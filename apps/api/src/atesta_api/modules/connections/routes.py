"""Connection endpoints (scanner-connectors spec, Endpoints): create, list, get, disconnect."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from atesta_core.connectors.readonly import GOOGLE_V1, M365_V1
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, StringConstraints

from atesta_api.modules.billing.api import require_connector_slot
from atesta_api.modules.connections import service
from atesta_api.modules.connections.models import Connection
from atesta_api.modules.identity.api import Member, Role, require_member, require_role
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/orgs/{org_id}/connections", tags=["connections"])
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code})


class ConnectionIn(BaseModel):
    provider: Literal["m365", "google_workspace"]
    display_name: DisplayName


class ConnectionOut(BaseModel):
    id: uuid.UUID
    provider: str
    status: str
    display_name: str
    allowlist_version: str | None
    created_at: datetime
    verified_at: datetime | None


class ExpectedAccess(BaseModel):
    """Exactly what the customer grants: the allowlist of the connection's version."""

    permissions: list[str]
    scan_scopes: list[str]
    verifier_scopes: list[str]


class LastVerification(BaseModel):
    """What the last verification found missing or extra, and what it cannot read."""

    missing: list[str]
    extra: list[str]
    limits: list[str]


class ConnectionDetail(ConnectionOut):
    google_client_id: str | None
    google_verifier_client_id: str | None
    expected_access: ExpectedAccess
    last_verification: LastVerification | None


def _last_verification(connection: Connection) -> LastVerification | None:
    report = connection.granted
    if not report:
        return None
    return LastVerification(
        missing=report["missing"], extra=report["extra"], limits=report["limits"]
    )


def _out(connection: Connection) -> ConnectionOut:
    return ConnectionOut.model_validate(connection, from_attributes=True)


def _expected(provider: str) -> ExpectedAccess:
    if provider == "m365":
        names = sorted(role.name for role in M365_V1.app_roles)
        return ExpectedAccess(permissions=names, scan_scopes=[], verifier_scopes=[])
    return ExpectedAccess(
        permissions=[],
        scan_scopes=sorted(GOOGLE_V1.scan_scopes),
        verifier_scopes=sorted(GOOGLE_V1.verifier_scopes),
    )


@router.post("", status_code=201)
def create_connection(
    body: ConnectionIn,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> ConnectionOut:
    in_use = sum(1 for c in service.list_connections(session) if c.status != "disconnected")
    require_connector_slot(session, member.organization_id, in_use)  # billing-entitlements spec
    connection = service.create_connection(
        session,
        organization_id=member.organization_id,
        provider=body.provider,
        display_name=body.display_name,
        created_by=member.user_id,
    )
    record(
        session,
        organization_id=member.organization_id,
        action="connection.created",
        target_type="connection",
        target_id=str(connection.id),
        actor_user_id=member.user_id,
        metadata={"provider": connection.provider},
    )
    return _out(connection)


@router.get("")
def list_connections(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[ConnectionOut]:
    return [_out(c) for c in service.list_connections(session)]


@router.get("/{connection_id}")
def get_connection(
    connection_id: uuid.UUID,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> ConnectionDetail:
    connection = service.get_connection(session, connection_id)
    if connection is None:
        raise _error(404, "connections.not_found")
    return ConnectionDetail(
        **_out(connection).model_dump(),
        google_client_id=connection.google_client_id,
        google_verifier_client_id=connection.google_verifier_client_id,
        expected_access=_expected(connection.provider),
        last_verification=_last_verification(connection),
    )


@router.delete("/{connection_id}")
def disconnect_connection(
    connection_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> ConnectionOut:
    try:
        connection = service.disconnect_connection(session, connection_id)
    except service.ConnectionStateError:
        raise _error(409, "connections.state_invalid") from None
    if connection is None:
        raise _error(404, "connections.not_found")
    record(
        session,
        organization_id=member.organization_id,
        action="connection.disconnected",
        target_type="connection",
        target_id=str(connection.id),
        actor_user_id=member.user_id,
        metadata={"provider": connection.provider},
    )
    return _out(connection)
