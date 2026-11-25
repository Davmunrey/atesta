"""Operator staff (operator-portal spec, ADR-017): who may use the operator service, and as what.

On an `atesta_operator` session. The account lives in the staff Cognito pool; the role lives
here, so a role is never read from the token. A disabled row, or none, is no access.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from atesta_api.modules.identity.for_operator import OperatorError
from atesta_api.modules.identity.models import OperatorStaff

type StaffRole = Literal["admin", "billing", "support"]
STAFF_ROLES: tuple[StaffRole, ...] = ("admin", "billing", "support")


@dataclass(frozen=True, slots=True)
class StaffMember:
    id: uuid.UUID
    email: str
    role: StaffRole
    disabled_at: datetime | None


_COLUMNS = (OperatorStaff.id, OperatorStaff.email, OperatorStaff.role, OperatorStaff.disabled_at)


def enabled_staff(session: Session, cognito_sub: str) -> StaffMember | None:
    """The enabled staff row for a staff-pool subject, or None (403 at the operator API)."""
    row = session.execute(
        select(*_COLUMNS).where(
            OperatorStaff.cognito_sub == cognito_sub, OperatorStaff.disabled_at.is_(None)
        )
    ).one_or_none()
    return None if row is None else _member(row.id, row.email, row.role, row.disabled_at)


def _member(id_: uuid.UUID, email: str, role: str, disabled_at: datetime | None) -> StaffMember:
    if role not in STAFF_ROLES:  # the table's CHECK holds the same list
        raise ValueError(f"unknown staff role {role!r}")
    return StaffMember(id_, email, role, disabled_at)


def staff_list(session: Session) -> list[StaffMember]:
    rows = session.execute(select(*_COLUMNS).order_by(OperatorStaff.email, OperatorStaff.id))
    return [_member(r.id, r.email, r.role, r.disabled_at) for r in rows]


def change_staff(
    session: Session,
    staff_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    role: StaffRole | None = None,
    disabled: bool | None = None,
) -> tuple[StaffMember, StaffMember]:
    """Change a colleague's role or access; returns the row before and after.

    Nobody changes their own row (`self_change`), and the last enabled admin is never demoted or
    disabled (`last_admin`). The enabled admins are locked first, so two admins demoting each
    other at once cannot both succeed.
    """
    if staff_id == actor_id:
        raise OperatorError("self_change")
    admins = session.scalars(
        select(OperatorStaff.id)
        .where(OperatorStaff.role == "admin", OperatorStaff.disabled_at.is_(None))
        .with_for_update()
    ).all()
    row = session.execute(
        select(*_COLUMNS).where(OperatorStaff.id == staff_id).with_for_update()
    ).one_or_none()
    if row is None:
        raise OperatorError("not_found")
    before = _member(row.id, row.email, row.role, row.disabled_at)
    new_role = before.role if role is None else role
    off = before.disabled_at is not None if disabled is None else disabled
    stays_admin = new_role == "admin" and not off
    if staff_id in admins and not stays_admin and len(admins) == 1:
        raise OperatorError("last_admin")
    changed = session.execute(
        update(OperatorStaff)
        .where(OperatorStaff.id == staff_id)
        .values(
            role=new_role,
            disabled_at=(before.disabled_at or func.now()) if off else None,
        )
        .returning(*_COLUMNS)
    ).one()
    return before, _member(changed.id, changed.email, changed.role, changed.disabled_at)


# --- the staff devtool (atesta_api.ops.staff, runbook "Staff accounts"), as atesta_owner --------


def staff_by_email(session: Session, email: str) -> StaffMember | None:
    row = session.execute(
        select(*_COLUMNS).where(func.lower(OperatorStaff.email) == email.lower())
    ).one_or_none()
    return None if row is None else _member(row.id, row.email, row.role, row.disabled_at)


def enabled_admins(session: Session) -> int:
    count = session.scalar(
        select(func.count()).where(
            OperatorStaff.role == "admin", OperatorStaff.disabled_at.is_(None)
        )
    )
    return int(count or 0)


def add_staff(session: Session, *, cognito_sub: str, email: str, role: StaffRole) -> StaffMember:
    """A new staff row for a staff-pool account (its `sub`). The account itself is created in
    the pool by an owner step; this row is what gives it a role."""
    row = session.execute(
        insert(OperatorStaff)
        .values(id=uuid.uuid4(), cognito_sub=cognito_sub, email=email.lower(), role=role)
        .returning(*_COLUMNS)
    ).one()
    return _member(row.id, row.email, row.role, row.disabled_at)
