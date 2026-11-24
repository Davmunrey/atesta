"""Deliver one notice to one person (notifications spec; issue 386).

Claim the delivery first, so a retried job never sends twice; then apply the person's choice,
compose in the organization's language and send. Nothing here logs an address, a token or a
body (rule 2): a failure is logged by type only.
"""

import logging
import time
import uuid
from datetime import UTC, date, datetime
from email.headerregistry import Address

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import OrganizationProfile, Recipient
from atesta_api.modules.notifications.config import mail_config
from atesta_api.modules.notifications.deliveries import claim_delivery
from atesta_api.modules.notifications.kinds import CRITICAL, Kind
from atesta_api.modules.notifications.mail import UnsubscribeLinks, compose
from atesta_api.modules.notifications.models import NotificationDelivery, NotificationPreference

SEND_ATTEMPTS = 3
_log = logging.getLogger("atesta.notifications")


def enabled(session: Session, organization_id: uuid.UUID, user_id: uuid.UUID, kind: Kind) -> bool:
    if kind in CRITICAL:
        return True
    stored = session.scalar(
        select(NotificationPreference.enabled).where(
            NotificationPreference.organization_id == organization_id,
            NotificationPreference.user_id == user_id,
            NotificationPreference.kind == kind.value,
        )
    )
    return True if stored is None else bool(stored)


def _finish(
    session: Session,
    organization_id: uuid.UUID,
    delivery_id: uuid.UUID,
    status: str,
    message_id: str | None = None,
) -> str:
    session.execute(
        update(NotificationDelivery)
        .where(
            NotificationDelivery.organization_id == organization_id,
            NotificationDelivery.id == delivery_id,
        )
        .values(
            status=status,
            provider_message_id=message_id,
            sent_at=datetime.now(UTC) if status == "sent" else None,
        )
    )
    return status


def sender(profile: OrganizationProfile, address: str) -> str:
    """ "Atesta · <organization>": quoted as RFC 5322 needs, so a name cannot break the header."""
    return str(Address(display_name=f"Atesta · {profile.name}", addr_spec=address))


def deliver(  # noqa: PLR0913 - one notice: who, what, where and its words
    session: Session,
    organization_id: uuid.UUID,
    recipient: Recipient,
    kind: Kind,
    dedupe_key: str,
    *,
    profile: OrganizationProfile,
    subject: str,
    lines: list[str],
    today: date,
) -> str:
    """`sent`, `suppressed`, `failed`, or `duplicate` when this one was already claimed."""
    delivery = claim_delivery(session, organization_id, recipient.user_id, kind, dedupe_key)
    if delivery is None:
        return "duplicate"
    config = mail_config()
    optional = kind not in CRITICAL
    if not enabled(session, organization_id, recipient.user_id, kind):
        return _finish(session, organization_id, delivery, "suppressed")
    if config is None or (optional and config.tokens is None):
        return _finish(session, organization_id, delivery, "suppressed")
    links = None
    if optional and config.tokens is not None:
        token = config.tokens.issue(organization_id, recipient.user_id, kind, today=today)
        links = UnsubscribeLinks.for_token(config.web_base_url, token)
    message = compose(
        to=recipient.email,
        sender=sender(profile, config.sender_address),
        kind=kind,
        locale=profile.locale,
        subject=subject,
        lines=lines,
        unsubscribe=links,
    )
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            message_id = config.mailer.send(message)
        except Exception:  # noqa: BLE001 - any provider error; logged by type, never content
            _log.warning("notification send failed", extra={"kind": kind.value, "attempt": attempt})
            if attempt < SEND_ATTEMPTS:
                time.sleep(attempt)
            continue
        return _finish(session, organization_id, delivery, "sent", message_id)
    return _finish(session, organization_id, delivery, "failed")
