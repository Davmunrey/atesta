"""The permissions matrix (operator-portal spec, "Permissions matrix" and "API"), in one place.

Every route is a key here, by method and path template. `authorize` looks the matched route up
and refuses anything not listed (deny by default), any role not listed for it, and a sign-in older
than 15 minutes where the rule asks for a recent one (spec, "Session limits"). Routes never check
roles themselves, and a test walks this table for every role and route.
"""

from dataclasses import dataclass

from atesta_api.modules.identity.api import STAFF_ROLES, StaffRole

ALL: frozenset[StaffRole] = frozenset(STAFF_ROLES)
BILLING: frozenset[StaffRole] = frozenset({"admin", "billing"})
ADMIN: frozenset[StaffRole] = frozenset({"admin"})
RECENT_SIGN_IN_SECONDS = 15 * 60


@dataclass(frozen=True, slots=True)
class Rule:
    roles: frozenset[StaffRole]
    recent_sign_in: bool = False


_V1 = "/api/v1"
_ORG = f"{_V1}/organizations/{{org_id}}"
POLICY: dict[tuple[str, str], Rule] = {
    ("GET", f"{_V1}/me"): Rule(ALL),
    ("GET", f"{_V1}/organizations"): Rule(ALL),
    ("GET", _ORG): Rule(ALL),
    ("PUT", f"{_ORG}/subscription"): Rule(BILLING),
    ("GET", f"{_ORG}/billing-profile"): Rule(BILLING),
    ("PUT", f"{_ORG}/billing-profile"): Rule(BILLING),
    ("POST", f"{_ORG}/suspension"): Rule(ADMIN, recent_sign_in=True),
    ("DELETE", f"{_ORG}/suspension"): Rule(ADMIN),
    ("POST", f"{_ORG}/export-request"): Rule(ADMIN),
    ("POST", f"{_ORG}/closure"): Rule(ADMIN, recent_sign_in=True),
    ("DELETE", f"{_ORG}/closure"): Rule(ADMIN),
    ("POST", f"{_ORG}/erasure-requests"): Rule(ADMIN, recent_sign_in=True),
    ("POST", f"{_V1}/erasure-requests/{{request_id}}/approval"): Rule(ADMIN, recent_sign_in=True),
    ("DELETE", f"{_V1}/erasure-requests/{{request_id}}"): Rule(ADMIN),
    ("GET", f"{_V1}/erasure-receipts"): Rule(ADMIN),
    ("GET", f"{_V1}/staff"): Rule(ADMIN),
    ("PATCH", f"{_V1}/staff/{{staff_id}}"): Rule(ADMIN),
    ("GET", f"{_V1}/operator-events"): Rule(ADMIN),
}
