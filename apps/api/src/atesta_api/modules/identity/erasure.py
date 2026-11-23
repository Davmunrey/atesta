"""Erasure of a closed organization (organization-closure spec, ADR-012 amendment 3).

Runs as atesta_owner from the operator command `erase_org` (outside this package), never from the
app. The deletion order comes from the database's own foreign keys, children first, so a table
added later is covered without code changes; a table outside platform.tables fails loudly.
"""

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from graphlib import TopologicalSorter

from sqlalchemy import Connection, Uuid, bindparam, column, delete, func, select, table, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from atesta_api.modules.identity.closure import GRACE
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
            {"id": uuid.uuid4(), "o": org_id, "r": requested_at, "n": note, "c": counts},
        )
    return counts
