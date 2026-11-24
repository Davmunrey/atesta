"""Service notices through an outbox (operator-portal spec, "Service notices"; ADR-012 amendment
12; owner choice "Bandeja de salida (Recomendado)", 2026-11-24).

- **Queue:** the operator service inserts one `service_notices` row in the transaction of the
  action that owes it (`queue_service_notice`, on an `atesta_operator` session). The role may
  only insert id, organization and kind: it cannot read, change or delete the outbox.
- **Send:** the worker reads the pending rows (ids and kinds only, no tenant context needed, as
  for the queue tables) and sends each in its organization's context (`send_service_notice`):
  owners, and admins for suspension and reactivation, in the organization's language. Each person
  is claimed once (`service:<notice id>`), and the row is marked sent in the same transaction.
- **Always:** nobody can turn these off, and they reach a suspended organization.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from sqlalchemy import column, insert, select, table, update
from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import (
    OrganizationMetadata,
    Role,
    organization_metadata,
    organization_profile,
    recipients,
)
from atesta_api.modules.notifications.config import mail_config
from atesta_api.modules.notifications.kinds import Kind
from atesta_api.modules.notifications.models import ServiceNotice
from atesta_api.modules.notifications.send import deliver
from atesta_api.modules.notifications.texts import day, madrid_day, text

SUPPORT_ADDRESS = "hello@atesta.cloud"  # the public contact address (spec, owner answer 9)
BATCH = 100


class ServiceNoticeKind(StrEnum):
    ORGANIZATION_SUSPENDED = "organization_suspended"
    ORGANIZATION_REACTIVATED = "organization_reactivated"
    EXPORT_REQUESTED = "export_requested"
    CLOSURE_STARTED_BY_OPERATOR = "closure_started_by_operator"


_TO_ADMINS_TOO = frozenset(
    {ServiceNoticeKind.ORGANIZATION_SUSPENDED, ServiceNoticeKind.ORGANIZATION_REACTIVATED}
)
# The columns atesta_operator may insert; nothing it could read back.
_OUTBOX = table("service_notices", column("id"), column("organization_id"), column("kind"))


def queue_service_notice(
    session: Session, organization_id: uuid.UUID, kind: ServiceNoticeKind
) -> uuid.UUID:
    """On an atesta_operator session, in the transaction of the action that owes the notice."""
    notice_id = uuid.uuid4()
    session.execute(
        insert(_OUTBOX).values(id=notice_id, organization_id=organization_id, kind=kind.value)
    )
    return notice_id


@dataclass(frozen=True, slots=True)
class PendingNotice:
    id: uuid.UUID
    organization_id: uuid.UUID
    kind: ServiceNoticeKind


def pending_service_notices(session: Session, limit: int = BATCH) -> list[PendingNotice]:
    """The oldest unsent notices; the outbox has no RLS and holds ids and kinds only."""
    rows = session.execute(
        select(ServiceNotice.id, ServiceNotice.organization_id, ServiceNotice.kind)
        .where(ServiceNotice.sent_at.is_(None))
        .order_by(ServiceNotice.created_at, ServiceNotice.id)
        .limit(limit)
    ).all()
    return [PendingNotice(r.id, r.organization_id, ServiceNoticeKind(r.kind)) for r in rows]


def _date(org: OrganizationMetadata, kind: ServiceNoticeKind) -> datetime | None:
    """The date a notice names, read when it is sent; None when what it announces no longer
    holds (reactivated, or the closure cancelled, before the worker ran)."""
    if kind is ServiceNoticeKind.ORGANIZATION_SUSPENDED:
        return org.suspended_at
    if kind is ServiceNoticeKind.CLOSURE_STARTED_BY_OPERATOR:
        return org.erase_after
    return None


_DATED = frozenset(
    {ServiceNoticeKind.ORGANIZATION_SUSPENDED, ServiceNoticeKind.CLOSURE_STARTED_BY_OPERATOR}
)


def _lines(
    session: Session, org: OrganizationMetadata, notice: PendingNotice, base_url: str
) -> tuple[str, list[str]]:
    profile = organization_profile(session, notice.organization_id)
    locale, key = profile.locale, f"service.{notice.kind.value}"
    values = {"org": profile.name, "email": SUPPORT_ADDRESS}
    moment = _date(org, notice.kind)
    if moment is not None:
        values["date"] = day(madrid_day(moment), locale)
    link = f"{base_url}/app/settings?org={notice.organization_id}"
    body = text(locale, f"{key}.body", **values)
    return text(locale, f"{key}.subject", **values), [body, "", text(locale, "open", url=link)]


def send_service_notice(session: Session, notice: PendingNotice, *, now: datetime) -> int:
    """In the organization's own context: send to each recipient once, then mark the row sent.
    Nothing is sent, and the row is marked all the same, when the organization was erased since
    or what the notice announces no longer holds."""
    sent = 0
    org = organization_metadata(session, notice.organization_id)
    stale = org is None or (notice.kind in _DATED and _date(org, notice.kind) is None)
    if org is not None and not stale:
        config = mail_config()
        roles = frozenset(
            {Role.OWNER, Role.ADMIN} if notice.kind in _TO_ADMINS_TOO else {Role.OWNER}
        )
        subject, lines = _lines(session, org, notice, config.web_base_url if config else "")
        profile = organization_profile(session, notice.organization_id)
        for person in recipients(session, notice.organization_id, roles):
            status = deliver(
                session,
                notice.organization_id,
                person,
                Kind.SERVICE_NOTICE,
                f"service:{notice.id}",
                profile=profile,
                subject=subject,
                lines=lines,
                today=madrid_day(now),
            )
            sent += status == "sent"
    session.execute(
        update(ServiceNotice)
        .where(ServiceNotice.id == notice.id, ServiceNotice.sent_at.is_(None))
        .values(sent_at=now)
    )
    return sent
