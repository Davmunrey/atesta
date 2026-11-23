"""The only code that enters an org context (ADR-012)."""

import uuid
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.platform.context import TenantContext
from atesta_api.platform.devenv import require_dev
from atesta_api.platform.tenancy import Organization, set_tenant_context


class ContextReason(StrEnum):
    MEMBERSHIP = "membership"
    INVITATION = "invitation"
    ORG_CREATION = "org_creation"
    JOB = "job"
    TRAINING_LINK = "training_link"  # ADR-012 amendment 4: a valid training link, no account


def enter_user_context(session: Session, subject: str, user_id: uuid.UUID | None = None) -> None:
    set_tenant_context(session, TenantContext(subject=subject, user_id=user_id))


def enter_invitation_context(session: Session, token_sha256: str) -> None:
    set_tenant_context(session, TenantContext(invitation_token_sha256=token_sha256))


def enter_training_link_context(session: Session, token_sha256: str) -> None:
    """Read one training campaign by its token's SHA-256 (policy training_token_read), before
    the organization is known. Writes still need enter_org_context(TRAINING_LINK)."""
    set_tenant_context(session, TenantContext(training_token_sha256=token_sha256))


def ensure_dev_organization(session: Session, org_id: uuid.UUID, name: str) -> None:
    """Dev tooling only: the bare org row of a fixed dev org, created once, in its own context."""
    require_dev("ensure_dev_organization")
    enter_org_context(session, org_id, ContextReason.JOB)
    statement = insert(Organization).values(id=org_id, name=name)
    session.execute(statement.on_conflict_do_nothing(index_elements=["id"]))


def enter_org_context(session: Session, org_id: uuid.UUID, reason: ContextReason) -> None:
    """Enter an org context once per transaction; switching orgs mid-transaction is refused."""
    current = session.execute(text("SELECT current_setting('app.organization_id', true)"))
    value = current.scalar()
    if value not in (None, "", str(org_id)):
        raise RuntimeError(f"transaction already in another org context ({reason})")
    set_tenant_context(session, TenantContext(organization_id=org_id))
