"""Preferences and one-click unsubscribe (notifications spec, PR 1; ADR-012 amendment 7)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from atesta_api.modules.identity.api import (
    ContextReason,
    Member,
    Role,
    enter_org_context,
    is_member,
    require_role,
)
from atesta_api.modules.notifications.digest import defer_daily
from atesta_api.modules.notifications.kinds import CRITICAL, Kind, receivable
from atesta_api.modules.notifications.models import NotificationPreference
from atesta_api.modules.notifications.tokens import TokenError, UnsubscribeTokens
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}/notifications", tags=["notifications"])
public_router = APIRouter(prefix="/api/v1", tags=["notifications"])


class PreferenceOut(BaseModel):
    kind: Kind
    enabled: bool
    can_disable: bool


class PreferenceIn(BaseModel):
    kind: Kind
    enabled: bool


class UnsubscribedOut(BaseModel):
    kind: Kind


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


def _preferences(session: DbSession, member: Member) -> list[PreferenceOut]:
    stored = {
        p.kind: p.enabled
        for p in session.scalars(
            select(NotificationPreference).where(
                NotificationPreference.organization_id == member.organization_id,
                NotificationPreference.user_id == member.user_id,
            )
        )
    }
    return [
        PreferenceOut(
            kind=kind,
            enabled=kind in CRITICAL or stored.get(kind.value, True),
            can_disable=kind not in CRITICAL,
        )
        for kind in receivable(member.role)
    ]


def _store(
    session: DbSession, organization_id: uuid.UUID, user_id: uuid.UUID, kind: Kind, enabled: bool
) -> None:
    statement = pg_insert(NotificationPreference).values(
        organization_id=organization_id, user_id=user_id, kind=kind.value, enabled=enabled
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["organization_id", "user_id", "kind"],
            set_={"enabled": enabled, "updated_at": datetime.now(UTC)},
        )
    )


@router.get("/preferences")
def read_preferences(
    member: Annotated[Member, Depends(require_role(Role.MEMBER))], session: DbSession
) -> list[PreferenceOut]:
    # Organizations created before the daily chain existed get it here; a no-op otherwise.
    defer_daily(session, member.organization_id, now=datetime.now(UTC))
    return _preferences(session, member)


@router.put("/preferences")
def change_preference(
    body: PreferenceIn,
    member: Annotated[Member, Depends(require_role(Role.MEMBER))],
    session: DbSession,
) -> list[PreferenceOut]:
    if body.kind in CRITICAL:
        raise _error(409, "notifications.not_optional")
    if body.kind not in receivable(member.role):
        raise _error(409, "notifications.not_available")
    _store(session, member.organization_id, member.user_id, body.kind, body.enabled)
    record(
        session,
        organization_id=member.organization_id,
        action="notification.preferences_changed",
        target_type="user",
        target_id=str(member.user_id),
        actor_user_id=member.user_id,
        metadata={"kind": body.kind.value, "enabled": body.enabled},
    )
    return _preferences(session, member)


@public_router.post("/unsubscribe")
def unsubscribe(request: Request, session: DbSession, token: str = "") -> UnsubscribedOut:
    """RFC 8058 one-click: a POST from the mail provider, nobody signed in."""
    tokens: UnsubscribeTokens | None = getattr(request.app.state, "notification_tokens", None)
    if tokens is None:
        raise _error(503, "notifications.unavailable")
    try:
        link = tokens.open(token, today=datetime.now(UTC).date())
    except TokenError:
        raise _error(400, "notifications.link_invalid") from None
    enter_org_context(session, link.organization_id, ContextReason.UNSUBSCRIBE_LINK)
    if not is_member(session, link.organization_id, link.user_id):
        raise _error(400, "notifications.link_invalid")  # a former member keeps no preference
    _store(session, link.organization_id, link.user_id, link.kind, False)
    record(
        session,
        organization_id=link.organization_id,
        action="notification.unsubscribed",
        target_type="user",
        target_id=str(link.user_id),
        actor_user_id=link.user_id,
        metadata={"kind": link.kind.value},
    )
    return UnsubscribedOut(kind=link.kind)
