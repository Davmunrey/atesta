"""The delivery log: one row per person, type and dedupe key (notifications spec, PR 1)."""

import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from atesta_api.modules.notifications.kinds import Kind
from atesta_api.modules.notifications.models import NotificationDelivery


def claim_delivery(
    session: Session, organization_id: uuid.UUID, user_id: uuid.UUID, kind: Kind, dedupe_key: str
) -> uuid.UUID | None:
    """A new queued delivery's id, or None when this one was already claimed (a retried job)."""
    statement = (
        pg_insert(NotificationDelivery)
        .values(
            organization_id=organization_id,
            user_id=user_id,
            kind=kind.value,
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(index_elements=["organization_id", "user_id", "kind", "dedupe_key"])
        .returning(NotificationDelivery.id)
    )
    return session.execute(statement).scalar_one_or_none()
