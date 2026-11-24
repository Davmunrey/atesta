"""Google Workspace read-only verification (scanner-connectors spec, Google verifier contract).

Step 1 mints a delegated token with each key for exactly its client's scopes, step 2 pins the
customer and checks the impersonated super admin, step 3 (the `verify` run only) reads the admin
audit log for each client's latest delegation change and every admin role assignment. The
verifier key reads the audit log and nothing else; the scan key reads the directory (D7). Fails
closed: a removal is `revoked`, anything extra `over_privileged`, anything missing or unreadable
`incomplete`, an outage `transient`, and nothing unread is ever `ok`. The report holds ids, scopes
and verdicts only; never an email, a token, a key or a Google message.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Protocol
from urllib.parse import quote

from atesta_core.connectors.google import is_customer_id
from atesta_core.connectors.readonly import GoogleGrants, check_google, google_allowlist

from atesta_scanner.entra_token import TokenTransientError
from atesta_scanner.google_api import GoogleDeniedError, GoogleTransientError
from atesta_scanner.google_token import ServiceAccountKey, TokenRefusedError

DIRECTORY = "admin/directory/v1/"
CUSTOMER = DIRECTORY + "customers/my_customer"
DOMAINS = DIRECTORY + "customer/my_customer/domains"
ROLE_ASSIGNMENTS = DIRECTORY + "customer/my_customer/roleassignments"
REPORTS = "admin/reports/v1/activity/users/all/applications/admin"
AUTHORIZE, REMOVE = "AUTHORIZE_API_CLIENT_ACCESS", "REMOVE_API_CLIENT_ACCESS"
OVERLAP = timedelta(hours=1)  # admin log events lag a few minutes (spec)

# Verifier limits (spec): recorded in every report, shown in onboarding.
GOOGLE_LIMITS = (
    "roles_through_groups_not_read",  # a role on a group holding a service account (candidate)
    "tokens_issued_before_revocation",
)


class GoogleReader(Protocol):
    def get(self, path: str, params: Mapping[str, str] | None = None) -> Any: ...
    def get_all(
        self, path: str, items_key: str, params: Mapping[str, str] | None = None
    ) -> list[Any]: ...


type Mint = Callable[[ServiceAccountKey, frozenset[str]], str]
type Read = Callable[[str], GoogleReader]


@dataclass(frozen=True, slots=True)
class GoogleTarget:
    subject: str  # the super admin to impersonate; never logged or reported
    tenant: str  # the pinned customer id, or before the first `ok` the entered primary domain
    unique_ids: tuple[str, ...]  # both service accounts' IAM uniqueIds
    since: datetime | None  # the last `ok` verification; None at activation
    version: str


@dataclass(frozen=True, slots=True)
class _Change:
    at: datetime
    removed: bool
    scopes: frozenset[str]


class _RefusedError(Exception):
    def __init__(self, missing: str) -> None:
        super().__init__(missing)
        self.missing = missing


def report(
    verdict: str,
    tenant_id: str | None = None,
    granted: Mapping[str, Sequence[str]] | None = None,
    missing: Sequence[str] = (),
    extra: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "tenant_id": tenant_id,
        "granted": {name: list(ids) for name, ids in (granted or {}).items()},
        "missing": list(missing),
        "extra": list(extra),
        "limits": list(GOOGLE_LIMITS),
    }


def _token(mint: Mint, key: ServiceAccountKey, scopes: frozenset[str], label: str) -> str:
    try:
        return mint(key, scopes)
    except TokenRefusedError as refused:
        reason = refused.reason
        raise _RefusedError(
            reason if reason == "delegated_user" else f"{label}_client_{reason}"
        ) from None


def _identity(directory: GoogleReader, target: GoogleTarget) -> tuple[str, list[str]]:
    """Step 2: the customer read, and what keeps it from being the connection's."""
    tenant_id = directory.get(CUSTOMER)["id"]
    if not isinstance(tenant_id, str) or not tenant_id:
        raise TypeError("customer without an id")
    pinned = is_customer_id(target.tenant)
    missing = ["customer_pin"] if pinned and tenant_id != target.tenant else []
    verified, primary = set(), set()
    for domain in directory.get(DOMAINS).get("domains", []):
        if domain.get("verified") is True:
            verified.add(str(domain["domainName"]).lower())
            if domain.get("isPrimary") is True:
                primary.add(str(domain["domainName"]).lower())
        for alias in domain.get("domainAliases", []):
            if alias.get("verified") is True:
                verified.add(str(alias["domainAliasName"]).lower())
    if not pinned and target.tenant.lower() not in primary:
        missing.append("primary_domain")
    if target.subject.rsplit("@", 1)[1].lower() not in verified:
        missing.append("delegated_user_domain")
    try:
        user = directory.get(DIRECTORY + "users/" + quote(target.subject, safe="@"))
    except GoogleDeniedError as denied:
        if denied.status != 404:
            raise
        return tenant_id, [*missing, "delegated_user"]
    if user.get("isAdmin") is not True:  # Google: `isAdmin` means super administrator
        missing.append("delegated_user_not_super_admin")
    if user.get("suspended") is True:
        missing.append("delegated_user_suspended")
    return tenant_id, missing


def _scopes(parameter: Mapping[str, Any]) -> frozenset[str]:
    values = parameter.get("multiValue")
    if values is None:
        values = re.split(r"[,\s]+", parameter["value"])
    if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
        raise TypeError("API_SCOPES is not a list of strings")
    return frozenset(value for value in values if value)


def _changes(
    reports: GoogleReader, clients: Mapping[str, str], since: datetime | None
) -> dict[str, _Change]:
    """Step 3: each client's latest delegation change (a removal wins at the same instant)."""
    latest: dict[str, _Change] = {}
    for name in (AUTHORIZE, REMOVE):
        params = {"eventName": name, "maxResults": "1000"}
        if since is not None:
            params["startTime"] = (since - OVERLAP).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        for activity in reports.get_all(REPORTS, "items", params):
            at = datetime.fromisoformat(activity["id"]["time"])
            if at.utcoffset() is None:
                raise ValueError("an audit event time without a zone")
            for event in activity["events"]:
                if event["name"] != name:
                    continue
                values = {parameter["name"]: parameter for parameter in event["parameters"]}
                label = clients.get(values["API_CLIENT_NAME"]["value"])
                if label is None:
                    continue  # another client: never this org's
                scopes = _scopes(values["API_SCOPES"]) if name == AUTHORIZE else frozenset()
                change = _Change(at, name == REMOVE, scopes)
                current = latest.get(label)
                if current is None or (change.at, change.removed) > (current.at, current.removed):
                    latest[label] = change
    return latest


def _held_roles(directory: GoogleReader, ids: frozenset[str]) -> list[str]:
    params = {"maxResults": "200"}
    assignments = directory.get_all(ROLE_ASSIGNMENTS, "items", params)
    return sorted(str(a["roleAssignmentId"]) for a in assignments if str(a["assignedTo"]) in ids)


def verify_google(
    mint: Mint,
    read: Read,
    target: GoogleTarget,
    scan_key: ServiceAccountKey,
    verifier_key: ServiceAccountKey | None = None,
) -> dict[str, Any]:
    """`verify` passes both keys (steps 1 to 3); a scan run passes the scan key only."""
    allowlist = google_allowlist(target.version)
    try:
        changes: dict[str, _Change] = {}
        if verifier_key is not None:
            verifier_token = _token(mint, verifier_key, allowlist.verifier_scopes, "verifier")
            scan_token, refusal = "", None
            try:
                scan_token = _token(mint, scan_key, allowlist.scan_scopes, "scan")
            except _RefusedError as refused:
                refusal = refused  # a removal in the audit log still reads as `revoked`
            clients = {scan_key.client_id: "scan", verifier_key.client_id: "verifier"}
            changes = _changes(read(verifier_token), clients, target.since)
            if any(change.removed for change in changes.values()):
                return report("revoked")
            if refusal is not None:
                raise refusal
        else:
            scan_token = _token(mint, scan_key, allowlist.scan_scopes, "scan")
        directory = read(scan_token)
        tenant_id, missing = _identity(directory, target)
        if missing:
            return report("incomplete", tenant_id, missing=missing)
        if verifier_key is None:
            return report("ok", tenant_id, {"scan_scopes": sorted(allowlist.scan_scopes)})
        ids = frozenset({*target.unique_ids, scan_key.client_id, verifier_key.client_id})
        roles = _held_roles(directory, ids)
    except _RefusedError as refused:
        return report("incomplete", missing=[refused.missing])
    except GoogleDeniedError:
        return report("incomplete", missing=["read access for verification"])
    except (
        GoogleTransientError,
        TokenTransientError,
        KeyError,
        TypeError,
        ValueError,
        AttributeError,
    ):
        return report("transient")
    held: dict[str, frozenset[str]] = {}
    for label, expected in (
        ("scan", allowlist.scan_scopes),
        ("verifier", allowlist.verifier_scopes),
    ):
        change = changes.get(label)
        if change is not None:
            held[label] = change.scopes
        else:  # no change since the last `ok`, or (activation) an event still in the log's lag
            held[label] = expected
            if target.since is None:
                missing.append(f"{label}_client_authorization_event")
    result = check_google(target.version, GoogleGrants(held["scan"], held["verifier"], len(roles)))
    missing += result.missing
    extra = list(result.extra)
    verdict = "over_privileged" if extra else "incomplete" if missing else "ok"
    granted = {
        "scan_scopes": sorted(held["scan"]),
        "verifier_scopes": sorted(held["verifier"]),
        "role_assignments": roles,
    }
    return report(verdict, tenant_id, granted, missing, extra)
