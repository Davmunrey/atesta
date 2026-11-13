"""The only code that enters an org context (ADR-012)."""

import uuid
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.orm import Session

from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context


class ContextReason(StrEnum):
    MEMBERSHIP = "membership"
    INVITATION = "invitation"
    ORG_CREATION = "org_creation"
    JOB = "job"


def enter_user_context(session: Session, subject: str, user_id: uuid.UUID | None = None) -> None:
    set_tenant_context(session, TenantContext(subject=subject, user_id=user_id))


def enter_invitation_context(session: Session, token_sha256: str) -> None:
    set_tenant_context(session, TenantContext(invitation_token_sha256=token_sha256))


def enter_org_context(session: Session, org_id: uuid.UUID, reason: ContextReason) -> None:
    """Enter an org context once per transaction; switching orgs mid-transaction is refused."""
    current = session.execute(text("SELECT current_setting('app.organization_id', true)"))
    value = current.scalar()
    if value not in (None, "", str(org_id)):
        raise RuntimeError(f"transaction already in another org context ({reason})")
    set_tenant_context(session, TenantContext(organization_id=org_id))
