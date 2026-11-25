"""Erasure of a closed organization (organization-closure spec, ADR-012 amendment 3).

Runs as atesta_owner from the erasure command (`atesta_api.ops.erase`, also `erase_org`), never
from the app, and only for an approved erasure request (operator-portal spec, "Erasure"). The
deletion order comes from the database's own foreign keys, children first, so a table
added later is covered without code changes; a table outside platform.tables fails loudly.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from graphlib import TopologicalSorter

from sqlalchemy import (
    Connection,
    Uuid,
    bindparam,
    column,
    delete,
    func,
    insert,
    select,
    table,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from atesta_api.modules.identity.closure import GRACE
from atesta_api.platform.audit import OperatorAuditEvent
from atesta_api.platform.tables import TENANT, TENANT_ROOT

_FKS = """
SELECT c.conrelid::regclass::text, c.confrelid::regclass::text
FROM pg_constraint c WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
"""


class ErasureRefusedError(RuntimeError):
    """The organization has not asked to close, or its grace period has not ended."""


def _order(conn: Connection) -> list[str]:
    """Tenant tables, each before the tables it references (children first)."""
    depends: dict[str, set[str]] = defaultdict(set)
    for child, parent in conn.execute(text(_FKS)).all():
        if child in TENANT and parent in TENANT and child != parent:
            depends[parent].add(child)  # the parent waits until its children are gone
    for name in TENANT:
        depends.setdefault(name, set())
    return list(TopologicalSorter(depends).static_order())


def erase_organization(
    conn: Connection,
    org_id: uuid.UUID,
    *,
    note: str,
    execute: bool,
    now: datetime | None = None,
    receipt_id: uuid.UUID | None = None,
) -> dict[str, int]:
    """Row counts per table that are (or, without execute, would be) deleted."""
    row = conn.execute(
        text("SELECT closure_requested_at FROM organizations WHERE id = :o"), {"o": org_id}
    ).first()
    if row is None or row[0] is None:
        raise ErasureRefusedError(f"{org_id}: no closure request")
    requested_at: datetime = row[0]
    if requested_at + GRACE > (now or datetime.now(UTC)):
        raise ErasureRefusedError(f"{org_id}: not due until {requested_at + GRACE:%Y-%m-%d}")
    user_ids = [
        u
        for (u,) in conn.execute(
            text(
                "SELECT m.user_id FROM memberships m WHERE m.organization_id = :o AND NOT EXISTS"
                " (SELECT 1 FROM memberships x WHERE x.user_id = m.user_id"
                " AND x.organization_id <> :o)"
            ),
            {"o": org_id},
        )
    ]
    counts: dict[str, int] = {}
    for name in [*_order(conn), TENANT_ROOT]:
        key = "id" if name == TENANT_ROOT else "organization_id"
        target = table(name, column(key, Uuid()))  # SQLAlchemy quotes the identifiers
        owned = target.c[key] == org_id
        counts[name] = conn.execute(
            select(func.count()).select_from(target).where(owned)
        ).scalar_one()
        if execute and counts[name]:
            conn.execute(delete(target).where(owned))
    erased_users = 0
    for user_id in user_ids:
        if not execute:
            erased_users += 1
            continue
        try:
            with conn.begin_nested():
                conn.execute(text("DELETE FROM users WHERE id = :u"), {"u": user_id})
            erased_users += 1
        except IntegrityError:
            pass  # still referenced elsewhere: kept, and absent from the count
    counts["users"] = erased_users
    if execute:
        conn.execute(
            text(
                "INSERT INTO erasure_receipts (id, organization_id, closure_requested_at, note,"
                " row_counts) VALUES (:id, :o, :r, :n, :c)"
            ).bindparams(bindparam("c", type_=JSONB)),
            {
                "id": receipt_id or uuid.uuid4(),
                "o": org_id,
                "r": requested_at,
                "n": note,
                "c": counts,
            },
        )
    return counts


# --- erasure requests (operator-portal spec, "Erasure"; the runner, #502) ---------------------

_REQUEST = """
SELECT organization_id, approved_at, cancelled_at, executed_at FROM erasure_requests WHERE id = :r
FOR UPDATE
"""
_DUE = """
SELECT r.id FROM erasure_requests r JOIN organizations o ON o.id = r.organization_id
WHERE r.approved_at IS NOT NULL AND r.cancelled_at IS NULL AND r.executed_at IS NULL
  AND o.closure_requested_at IS NOT NULL AND o.closure_requested_at + :grace <= :now
ORDER BY r.approved_at, r.id
"""


# An operator-trail action (staff NULL: the runner), never a customer Activity action.
RUNNER_ACTION = "erasure.executed"


@dataclass(frozen=True, slots=True)
class ErasureRun:
    request_id: uuid.UUID
    organization_id: uuid.UUID
    receipt_id: uuid.UUID | None  # None for a dry run
    rows: dict[str, int]


def due_erasure_requests(conn: Connection, now: datetime | None = None) -> list[uuid.UUID]:
    """Approved, open requests whose organization's closure date has passed."""
    found = conn.execute(text(_DUE), {"grace": GRACE, "now": now or datetime.now(UTC)})
    return [request for (request,) in found]


def run_erasure_request(
    conn: Connection, request_id: uuid.UUID, *, execute: bool, now: datetime | None = None
) -> ErasureRun:
    """Erase the organization of an approved, uncancelled, unexecuted request whose closure date
    has passed. Executing also marks the request with its receipt and writes `erasure.executed`
    to the operator trail (no staff: the runner), in the caller's transaction."""
    row = conn.execute(text(_REQUEST), {"r": request_id}).first()
    if row is None:
        raise ErasureRefusedError(f"{request_id}: no erasure request")
    if row.executed_at is not None:
        raise ErasureRefusedError(f"{request_id}: already executed")
    if row.cancelled_at is not None:
        raise ErasureRefusedError(f"{request_id}: cancelled")
    if row.approved_at is None:
        raise ErasureRefusedError(f"{request_id}: not approved")
    org_id: uuid.UUID = row.organization_id
    receipt = uuid.uuid4() if execute else None
    note = f"erasure request {request_id}"
    rows = erase_organization(conn, org_id, note=note, execute=execute, now=now, receipt_id=receipt)
    if receipt is not None:
        conn.execute(
            text("UPDATE erasure_requests SET executed_at = now(), receipt_id = :c WHERE id = :r"),
            {"c": receipt, "r": request_id},
        )
        conn.execute(
            insert(OperatorAuditEvent).values(
                id=uuid.uuid4(),
                action=RUNNER_ACTION,
                organization_id=org_id,
                target_id=str(request_id),
                details={"receipt_id": str(receipt)},
            )
        )
    return ErasureRun(request_id, org_id, receipt, rows)
