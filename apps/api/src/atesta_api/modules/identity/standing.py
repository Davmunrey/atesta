"""An organization's standing: suspension and the ended trial (operator-portal spec; owner
answer 1).

`enforce` is the one enforcement point, like ADR-009's entitlements gate: `require_member` and the
API-key check call it after entering the organization's context, so no route can forget it.
- **Suspended:** every route answers 403 `identity.organization_suspended`, except what owners
  keep (GDPR art. 20): export, their own closure, and the billing details.
- **Trial ended without a plan:** the organization is read-only. Every write answers 403
  `billing.trial_ended`; owners can still close, and anyone keeps their notification choices.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.billing.api import has_plan
from atesta_api.platform.i18n import Locale, message
from atesta_api.platform.tenancy import Organization

ORG = "/api/v1/orgs/{org_id}"
CLOSURE = (("POST", f"{ORG}/closure"), ("DELETE", f"{ORG}/closure"))
OWNERS_WHILE_SUSPENDED = frozenset(
    {("GET", f"{ORG}/export"), *CLOSURE, ("GET", f"{ORG}/billing-profile")}
)
OWNER_WRITES_AFTER_TRIAL = frozenset(CLOSURE)
WRITES_AFTER_TRIAL = frozenset({("PUT", f"{ORG}/notifications/preferences")})  # a person's choice
WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@dataclass(frozen=True, slots=True)
class Standing:
    suspended: bool
    trial_ends_at: datetime
    trial_ended: bool  # the date has passed and the operator has set no plan


def standing(session: Session, org_id: uuid.UUID) -> Standing:
    """In the organization's own context: one primary-key read, and the plan only once the
    trial date has passed."""
    row = session.execute(
        select(Organization.suspended_at, Organization.trial_ends_at).where(
            Organization.id == org_id
        )
    ).one()
    ended = row.trial_ends_at <= datetime.now(UTC) and not has_plan(session, org_id)
    return Standing(row.suspended_at is not None, row.trial_ends_at, ended)


def is_suspended(session: Session, org_id: uuid.UUID) -> bool:
    """For jobs and public links, in the organization's context: no scan, notice or training
    confirmation while suspended."""
    since = session.scalar(select(Organization.suspended_at).where(Organization.id == org_id))
    return since is not None


def enforce(
    session: Session,
    org_id: uuid.UUID,
    *,
    method: str,
    path: str,
    owner: bool,
    language: Locale | None = None,
) -> None:
    """Refuse what the organization's standing does not allow. `path` is the request's own path,
    matched exactly against the allowlists filled with this organization: anything else is
    refused. `language` adds the message an API key's caller reads (api-keys-v2 spec)."""
    state = standing(session, org_id)
    call = (method, path.replace(str(org_id), "{org_id}"))
    if state.suspended and not (owner and call in OWNERS_WHILE_SUSPENDED):
        raise _refused({"code": "identity.organization_suspended"}, language)
    if (
        state.trial_ended
        and method in WRITES
        and call not in WRITES_AFTER_TRIAL
        and not (owner and call in OWNER_WRITES_AFTER_TRIAL)
    ):
        raise _refused({"code": "billing.trial_ended"}, language)


def _refused(detail: dict[str, str], language: Locale | None) -> HTTPException:
    if language is not None:
        detail["message"] = message(language, f"standing.{detail['code'].split('.')[1]}")
    return HTTPException(status_code=403, detail=detail)
