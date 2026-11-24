"""Connection health for the operator service (operator-portal spec, "Metadata fields").

Status counts only, read on an atesta_operator session: never a display name, tenant id or domain.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from atesta_api.modules.connections.models import Connection

ATTENTION = frozenset({"incomplete", "over_privileged", "revoked"})
type Health = Literal["none", "ok", "attention", "pending"]


@dataclass(frozen=True, slots=True)
class ConnectionHealth:
    by_provider: dict[str, dict[str, int]] = field(default_factory=dict)

    def _count(self, keep: bool) -> int:
        return sum(
            n
            for statuses in self.by_provider.values()
            for status, n in statuses.items()
            if (status != "disconnected") == keep
        )

    @property
    def in_use(self) -> int:
        """Connections that count against the plan's connector limit."""
        return self._count(keep=True)

    @property
    def health(self) -> Health:
        """`pending` while one is still being set up or verified, and none needs attention."""
        statuses = {s for by in self.by_provider.values() for s, n in by.items() if n}
        statuses.discard("disconnected")
        if not statuses:
            return "none"
        if statuses & ATTENTION:
            return "attention"
        return "ok" if statuses == {"active"} else "pending"


def health_counts(
    session: Session, org_ids: Collection[uuid.UUID] | None
) -> dict[uuid.UUID, ConnectionHealth]:
    """Counts by provider and status per organization with a connection; None reads all."""
    query = select(
        Connection.organization_id, Connection.provider, Connection.status, func.count()
    ).group_by(Connection.organization_id, Connection.provider, Connection.status)
    if org_ids is not None:
        query = query.where(Connection.organization_id.in_(org_ids))
    found: dict[uuid.UUID, ConnectionHealth] = {}
    for org_id, provider, status, count in session.execute(query):
        found.setdefault(org_id, ConnectionHealth()).by_provider.setdefault(provider, {})[
            status
        ] = count
    return found
