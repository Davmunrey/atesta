"""Operator staff (operator-portal spec, ADR-017): who may use the operator service, and as what.

On an `atesta_operator` session. The account lives in the staff Cognito pool; the role lives
here, so a role is never read from the token. A disabled row, or none, is no access.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

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
