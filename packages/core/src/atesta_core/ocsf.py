"""Strict reading of Prowler's OCSF Detection Findings (scanner-connectors spec, ingest).

Only the fields Atesta keeps are read; anything else is ignored. Every string is untrusted data
(rule 5), and error messages name the finding and the field, never a value from the output, so
errors and logs never carry tenant data (rule 2).
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

# Prowler 5.49.0 (lib/outputs/ocsf/ocsf.py): status_code is the check status, status is
# "Suppressed" when the finding is muted, severity is a py_ocsf_models SeverityID name.
_STATUS = {"PASS": "pass", "FAIL": "fail", "MANUAL": "manual"}
_MUTED = {"New": False, "Suppressed": True}
_SEVERITIES = frozenset(
    {"Unknown", "Informational", "Low", "Medium", "High", "Critical", "Fatal", "Other"}
)
# M365 findings carry the tenant GUID in cloud.org.uid; Google ones the customer id in
# cloud.account.uid (Prowler 5.49.0 lib/outputs/finding.py).
_TENANT_FIELD = {"m365": "org_uid", "google_workspace": "account_uid"}

type _Path = tuple[str | int, ...]


class OcsfError(ValueError):
    """The engine output is not what Atesta reads."""


class TenantMismatchError(ValueError):
    """A finding belongs to another tenant: the whole scan is rejected."""


@dataclass(frozen=True, slots=True)
class OcsfFinding:
    check_id: str
    status: str
    muted: bool
    severity: str
    service: str
    resource_type: str
    resource_uid: str
    resource_name: str
    region: str
    message: str
    account_uid: str | None
    org_uid: str | None


def _walk(item: object, path: _Path) -> object:
    for key in path:
        if isinstance(key, int):
            if not isinstance(item, list) or len(item) <= key:
                raise KeyError(key)
            item = item[key]
        else:
            if not isinstance(item, dict) or key not in item:
                raise KeyError(key)
            item = item[key]
    return item


def _text(item: object, index: int, *path: str | int) -> str:
    field = ".".join(map(str, path))
    try:
        value = _walk(item, path)
    except KeyError:
        raise OcsfError(f"finding {index}: missing {field}") from None
    if not isinstance(value, str):
        raise OcsfError(f"finding {index}: {field} is not text")
    return _storable(value, index, field)


def _storable(value: str, index: int, field: str) -> str:
    """PostgreSQL text cannot hold NUL: such a value would fail ingest outside its error path."""
    if "\x00" in value:
        raise OcsfError(f"finding {index}: {field} contains a NUL character")
    return value


def _optional_text(item: object, index: int, *path: str | int) -> str | None:
    try:
        value = _walk(item, path)
    except KeyError:
        return None
    return _storable(value, index, ".".join(map(str, path))) if isinstance(value, str) else None


def _finding(item: object, index: int) -> OcsfFinding:
    if not isinstance(item, dict):
        raise OcsfError(f"finding {index}: not an object")
    status = _STATUS.get(_text(item, index, "status_code"))
    if status is None:
        raise OcsfError(f"finding {index}: unknown status_code")
    state = _text(item, index, "status")
    if state not in _MUTED:
        raise OcsfError(f"finding {index}: unknown status")
    severity = _text(item, index, "severity")
    if severity not in _SEVERITIES:
        raise OcsfError(f"finding {index}: unknown severity")
    return OcsfFinding(
        check_id=_text(item, index, "metadata", "event_code"),
        status=status,
        muted=_MUTED[state],
        severity=severity.lower(),
        service=_text(item, index, "resources", 0, "group", "name"),
        resource_type=_text(item, index, "resources", 0, "type"),
        resource_uid=_text(item, index, "resources", 0, "uid"),
        resource_name=_text(item, index, "resources", 0, "name"),
        region=_text(item, index, "resources", 0, "region"),
        message=_text(item, index, "status_detail"),
        account_uid=_optional_text(item, index, "cloud", "account", "uid"),
        org_uid=_optional_text(item, index, "cloud", "org", "uid"),
    )


def parse_findings(raw: bytes) -> list[OcsfFinding]:
    """Parse Prowler's json-ocsf output: one JSON array of Detection Findings."""
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError):  # UnicodeDecodeError; nesting too deep
        raise OcsfError("output is not JSON") from None
    if not isinstance(data, list):
        raise OcsfError("output is not an array of findings")
    return [_finding(item, index) for index, item in enumerate(data)]


def pin_tenant(findings: Sequence[OcsfFinding], provider: str, tenant: str) -> None:
    """Every finding must belong to the connected tenant; one mismatch rejects the scan."""
    field = _TENANT_FIELD.get(provider)
    if field is None:
        raise ValueError("unknown provider for the pin")
    if not tenant:
        raise ValueError("the pin needs the expected tenant")
    for index, finding in enumerate(findings):
        if getattr(finding, field) != tenant:
            raise TenantMismatchError(f"finding {index} belongs to another tenant")
