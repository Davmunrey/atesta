"""The job file a run receives (scanner-connectors spec, Scan lifecycle): ids, never a secret."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atesta_core.connectors.google import (
    is_customer_id,
    is_domain,
    is_service_account_id,
    is_subject_email,
)

from atesta_scanner.invocation import prowler_argv

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_KEYS = frozenset(
    {"organization_id", "scan_id", "attempt", "provider", "tenant", "excluded", "allowlist_version"}
)
_VERSIONS = {"m365": frozenset({"m365-v1"}), "google_workspace": frozenset({"google-v1"})}
_GOOGLE = frozenset({"google_subject", "google_service_accounts"})
_ALLOWED = {  # (required, optional) keys beyond _KEYS
    "m365": (frozenset(), frozenset({"admin_oid", "credential_ref"})),
    "google_workspace": (
        _GOOGLE,
        frozenset({"verified_since", "credential_ref", "verifier_credential_ref"}),
    ),
}
# A reference the wrapper reads in AWS (issue 444), never a secret: a Secrets Manager ARN in
# eu-south-2, or a local file name (the local runner reads its own store and ignores it).
_REF = re.compile(
    r"aws-sm:arn:aws:secretsmanager:eu-south-2:[0-9]{12}:secret:[A-Za-z0-9/_+=.@-]{1,512}"
    r"|local:[a-z0-9][a-z0-9-]{0,62}"
)


class JobError(ValueError):
    """job.json is not what the worker writes."""


@dataclass(frozen=True, slots=True)
class Job:
    organization_id: str
    scan_id: str
    attempt: int
    provider: str
    tenant: str
    excluded: tuple[str, ...]
    allowlist_version: str  # the verifier compares grants with this version's expected set
    admin_oid: str | None = None  # activation only: the consenting admin to bind (step 6, #331)
    # Google only (issue 390): the super admin to impersonate (never logged), both service
    # accounts' IAM uniqueIds, and the last `ok` verification the audit log is re-read from.
    google_subject: str | None = field(default=None, repr=False)
    google_service_accounts: tuple[str, ...] = ()
    verified_since: datetime | None = None
    # Where the run's credential lives (issue 444): the scan key or certificate, and for a
    # Google verify run the verifier key. The Fargate wrapper reads them with its task role.
    credential_ref: str | None = None
    verifier_credential_ref: str | None = None


def _google(data: dict[str, Any]) -> dict[str, Any]:
    subject, accounts = data["google_subject"], data["google_service_accounts"]
    if not (isinstance(subject, str) and is_subject_email(subject)):
        raise JobError("job google_subject is not an email")
    if not (
        isinstance(accounts, list)
        and len(accounts) == 2
        and len(set(accounts)) == 2
        and all(isinstance(a, str) and is_service_account_id(a) for a in accounts)
    ):
        raise JobError("job google_service_accounts must be two numeric ids")
    tenant = data["tenant"]
    if not (isinstance(tenant, str) and (is_customer_id(tenant) or is_domain(tenant))):
        raise JobError("job google tenant is neither a customer id nor a domain")
    since = data.get("verified_since")
    if since is not None:
        try:
            since = datetime.fromisoformat(since) if isinstance(since, str) else None
        except ValueError:
            since = None
        if since is None or since.utcoffset() is None:
            raise JobError("job verified_since is not a time with a zone")
    return {
        "google_subject": subject,
        "google_service_accounts": tuple(accounts),
        "verified_since": since,
    }


def load_job(raw: bytes) -> Job:
    try:
        data = json.loads(raw)
    except ValueError:
        raise JobError("job.json is not JSON") from None
    if not isinstance(data, dict) or data.get("provider") not in _ALLOWED:
        raise JobError("job.json names no known provider")
    required, optional = _ALLOWED[data["provider"]]
    extra = data.keys() - _KEYS - required
    if not (_KEYS | required) <= data.keys() or not extra <= optional:
        raise JobError("job.json has unexpected or missing keys")
    admin_oid = data.get("admin_oid")
    # A GUID only: it is placed in a Graph $filter, so nothing else may reach the query.
    if admin_oid is not None and not (isinstance(admin_oid, str) and _UUID.fullmatch(admin_oid)):
        raise JobError("job admin_oid is not a GUID")
    ids = (data["organization_id"], data["scan_id"])
    if not all(isinstance(i, str) and _UUID.fullmatch(i) for i in ids):
        raise JobError("job ids are not UUIDs")
    attempt, tenant, excluded = data["attempt"], data["tenant"], data["excluded"]
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise JobError("job attempt must be 1 or more")
    if not isinstance(tenant, str) or not tenant:
        raise JobError("job has no tenant to pin")
    if not isinstance(excluded, list) or not all(isinstance(c, str) for c in excluded):
        raise JobError("job excluded checks must be a list of check ids")
    try:
        prowler_argv(data["provider"], excluded)  # validates the provider and every check id
    except ValueError as error:
        raise JobError(str(error)) from None
    version = data["allowlist_version"]
    if version not in _VERSIONS[data["provider"]]:
        raise JobError("job allowlist version is not one of the provider's")
    google = _google(data) if data["provider"] == "google_workspace" else {}
    refs = {
        name: data[name] for name in ("credential_ref", "verifier_credential_ref") if name in data
    }
    if not all(isinstance(ref, str) and _REF.fullmatch(ref) for ref in refs.values()):
        raise JobError("job credential refs are not references")
    return Job(
        *ids,
        attempt,
        data["provider"],
        tenant,
        tuple(sorted(excluded)),
        version,
        admin_oid,
        **google,
        credential_ref=refs.get("credential_ref"),
        verifier_credential_ref=refs.get("verifier_credential_ref"),
    )
