"""Organization export and closure request (organization-closure spec). Owners only.

The export reads every tenant table under the organization's RLS context; erasure itself is an
operator command (erasure.py), never an API call.
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from atesta_api.modules.identity.deps import Member, error, require_role
from atesta_api.modules.identity.models import Membership, Role, User
from atesta_api.platform.audit import record
from atesta_api.platform.db import Base, DbSession
from atesta_api.platform.tables import TENANT
from atesta_api.platform.tenancy import Organization

router = APIRouter(prefix="/orgs/{org_id}")  # mounted under /v1 by routes.py

GRACE = timedelta(days=30)
FORMAT = "atesta-organization-export/1"
# Columns that only reference secrets, or hash them: never leave the database (CLAUDE.md rule 2).
EXCLUDED = {
    "invitations": {"token_sha256"},
    "connections": {"credential_ref", "verifier_credential_ref"},
}


def erase_after(requested_at: datetime | None) -> datetime | None:
    return None if requested_at is None else requested_at + GRACE


def _plain(value: object) -> Any:
    if isinstance(value, uuid.UUID | Decimal):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


@router.get("/export")
def export_organization(
    member: Annotated[Member, Depends(require_role(Role.OWNER))], session: DbSession
) -> Response:
    org_id = member.organization_id
    organization = session.get(Organization, org_id)
    if organization is None:
        raise error(404, "identity.not_found")
    tables: dict[str, list[dict[str, Any]]] = {}
    for name in sorted(TENANT):
        table = Base.metadata.tables[name]
        hidden = EXCLUDED.get(name, set())
        rows = session.execute(select(table).where(table.c.organization_id == org_id)).mappings()
        tables[name] = [{k: _plain(v) for k, v in row.items() if k not in hidden} for row in rows]
    members = session.execute(
        select(User.email, User.display_name)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.organization_id == org_id)
        .order_by(User.email)
    ).all()
    record(
        session,
        organization_id=org_id,
        action="organization.exported",
        target_type="organization",
        target_id=str(org_id),
        actor_user_id=member.user_id,
        metadata={f"rows.{name}": len(rows) for name, rows in tables.items()},
    )
    body = {
        "format": FORMAT,
        "exported_at": datetime.now(UTC).isoformat(),
        "organization": {
            "id": str(organization.id),
            "name": organization.name,
            "created_at": organization.created_at.isoformat(),
        },
        "members": [{"email": e, "display_name": d} for e, d in members],
        "tables": tables,
    }
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    return Response(
        json.dumps(body, ensure_ascii=False, indent=1),
        media_type="application/json",
        headers={
            "content-disposition": f'attachment; filename="atesta-export-{org_id}-{stamp}.json"'
        },
    )


class ClosureIn(BaseModel):
    confirm_name: str = Field(max_length=300)


class ClosureOut(BaseModel):
    requested_at: datetime
    erase_after: datetime


@router.post("/closure", status_code=202)
def request_closure(
    body: ClosureIn,
    member: Annotated[Member, Depends(require_role(Role.OWNER))],
    session: DbSession,
) -> ClosureOut:
    organization = session.get(Organization, member.organization_id)
    if organization is None:
        raise error(404, "identity.not_found")
    if body.confirm_name != organization.name:
        raise error(422, "identity.closure_name_mismatch")
    if organization.closure_requested_at is None:
        organization.closure_requested_at = datetime.now(UTC)
        organization.closure_requested_by = member.user_id
        session.flush()
        record(
            session,
            organization_id=organization.id,
            action="organization.closure_requested",
            target_type="organization",
            target_id=str(organization.id),
            actor_user_id=member.user_id,
        )
    requested = organization.closure_requested_at
    return ClosureOut(requested_at=requested, erase_after=requested + GRACE)


@router.delete("/closure", status_code=204)
def cancel_closure(
    member: Annotated[Member, Depends(require_role(Role.OWNER))], session: DbSession
) -> Response:
    origin = session.scalar(
        select(Organization.closure_origin).where(Organization.id == member.organization_id)
    )
    if origin == "operator":  # only an operator admin cancels it (owner answer 8)
        raise error(409, "identity.closure_by_operator")
    cancelled = session.execute(
        update(Organization)
        .where(
            Organization.id == member.organization_id,
            Organization.closure_requested_at.is_not(None),
        )
        .values(closure_requested_at=None, closure_requested_by=None)
        .returning(Organization.id)
    ).scalar()
    if cancelled is None:
        raise error(404, "identity.not_found")
    record(
        session,
        organization_id=member.organization_id,
        action="organization.closure_cancelled",
        target_type="organization",
        target_id=str(member.organization_id),
        actor_user_id=member.user_id,
    )
    return Response(status_code=204)
