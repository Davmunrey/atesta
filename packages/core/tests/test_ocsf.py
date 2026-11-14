"""Strict OCSF parsing and the tenant pin, against the synthetic Prowler 5.49.0 fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest
from atesta_core.ocsf import (
    OcsfError,
    OcsfFinding,
    TenantMismatchError,
    parse_findings,
    pin_tenant,
)
from py_ocsf_models.events.findings.detection_finding import DetectionFinding

FIXTURES = Path(__file__).resolve().parents[3] / "scanner" / "fixtures" / "synthetic"
M365_TENANT = "11111111-1111-4111-8111-111111111111"
GWS_CUSTOMER = "C0fixture1"


def raw(provider: str, name: str) -> bytes:
    return (FIXTURES / provider / name).read_bytes()


def items(provider: str = "m365", name: str = "scan.ocsf.json") -> list[dict[str, Any]]:
    loaded: list[dict[str, Any]] = json.loads(raw(provider, name))
    return loaded


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*/*.ocsf.json")), ids=lambda p: p.name)
def test_fixtures_are_detection_findings_as_prowler_writes_them(path: Path) -> None:
    for item in json.loads(path.read_bytes()):
        DetectionFinding.model_validate(item)


def test_kept_fields_are_mapped_from_prowler_output() -> None:
    findings = parse_findings(raw("m365", "scan.ocsf.json"))
    assert [(f.check_id, f.status, f.muted, f.severity, f.service) for f in findings] == [
        ("entra_admin_users_mfa_enabled", "pass", False, "high", "entra"),
        ("entra_admin_users_cloud_only", "fail", False, "high", "entra"),
        ("entra_admin_consent_workflow_enabled", "fail", True, "high", "entra"),
        ("exchange_mailbox_audit_bypass_disabled", "manual", False, "high", "exchange"),
        ("exchange_external_email_tagging_enabled", "pass", False, "medium", "exchange"),
    ]
    assert findings[0] == OcsfFinding(
        check_id="entra_admin_users_mfa_enabled",
        status="pass",
        muted=False,
        severity="high",
        service="entra",
        resource_type="NotDefined",
        resource_uid="admin-1",
        resource_name="Admin One",
        region="global",
        message="Synthetic PASS for Admin One.",
        account_uid="fixture.onmicrosoft.com",
        org_uid=M365_TENANT,
    )


def test_unknown_fields_are_ignored() -> None:
    data = items()
    data[0]["unmapped"] = {"anything": ["goes"]}
    data[0]["new_ocsf_field"] = 1
    assert parse_findings(json.dumps(data).encode())[0].check_id == "entra_admin_users_mfa_enabled"


def _set(item: dict[str, Any], path: str, value: Any) -> None:
    *parents, last = path.split(".")
    for key in parents:
        item = item[key] if not key.isdigit() else item[int(key)]  # type: ignore[index]
    if value is _DELETE:
        del item[last]
    else:
        item[last] = value


_DELETE = object()
MALFORMED = {
    "no check id": ("metadata.event_code", _DELETE),
    "check id not text": ("metadata.event_code", 7),
    "unknown status code": ("status_code", "ERROR-xyz-secret"),
    "unknown status": ("status", "Weird-xyz-secret"),
    "unknown severity": ("severity", "Dire-xyz-secret"),
    "no resource": ("resources", []),
    "resource without uid": ("resources.0.uid", _DELETE),
    "no message": ("status_detail", _DELETE),
    # PostgreSQL text cannot hold NUL: accepted here, the ingest would fail outside its error path.
    "NUL in a resource name": ("resources.0.name", "secret\u0000name"),
    "NUL in the message": ("status_detail", "secret\u0000detail"),
    "NUL in an optional tenant field": ("cloud.account.uid", "secret\u0000tenant"),
}


@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_malformed_findings_are_rejected_without_echoing_values(name: str) -> None:
    data = items()
    _set(data[1], *MALFORMED[name])
    with pytest.raises(OcsfError) as exc:
        parse_findings(json.dumps(data).encode())
    assert "finding 1" in str(exc.value)
    assert "secret" not in str(exc.value)  # rule 2: no output values in errors or logs


@pytest.mark.parametrize(
    "payload", [b"not json", b'{"a": 1}', b"[1, 2]", b"\xff\xfe", b"[" * 200_000]
)
def test_output_that_is_not_a_finding_array_is_rejected(payload: bytes) -> None:
    with pytest.raises(OcsfError):
        parse_findings(payload)


def test_an_m365_scan_is_pinned_to_its_tenant_guid() -> None:
    pin_tenant(parse_findings(raw("m365", "scan.ocsf.json")), "m365", M365_TENANT)
    with pytest.raises(TenantMismatchError, match="finding 5"):
        pin_tenant(parse_findings(raw("m365", "wrong-tenant.ocsf.json")), "m365", M365_TENANT)


def test_a_google_scan_is_pinned_to_its_customer_id() -> None:
    findings = parse_findings(raw("googleworkspace", "scan.ocsf.json"))
    pin_tenant(findings, "google_workspace", GWS_CUSTOMER)
    with pytest.raises(TenantMismatchError):
        pin_tenant(findings, "google_workspace", "C0fixture2")
    wrong = parse_findings(raw("googleworkspace", "wrong-tenant.ocsf.json"))
    with pytest.raises(TenantMismatchError, match="finding 4"):
        pin_tenant(wrong, "google_workspace", GWS_CUSTOMER)


def test_a_pin_needs_a_known_provider_and_a_tenant() -> None:
    findings = parse_findings(raw("m365", "scan.ocsf.json"))
    with pytest.raises(ValueError, match="provider"):
        pin_tenant(findings, "aws", M365_TENANT)
    with pytest.raises(ValueError, match="tenant"):
        pin_tenant(findings, "m365", "")
