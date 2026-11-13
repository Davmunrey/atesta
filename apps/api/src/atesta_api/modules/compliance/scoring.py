"""Score snapshots from active catalog rows (control-model spec). Scoring logic stays in core."""

import os
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from atesta_core.frameworks import Mapping as CoreMapping
from atesta_core.frameworks import framework_results, group_scores
from atesta_core.scoring import ControlResult, Status, score
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import (
    Control,
    Framework,
    Requirement,
    ScoreSnapshot,
)
from atesta_api.modules.compliance.models import (
    Mapping as MappingRow,
)


def include_drafts() -> bool:
    """Dev may score draft packs; production refuses to start with the flag (rule 10)."""
    enabled = os.environ.get("ATESTA_CATALOG_INCLUDE_DRAFTS") == "true"
    if enabled and os.environ.get("ATESTA_ENV") == "prod":
        raise RuntimeError("ATESTA_CATALOG_INCLUDE_DRAFTS is not allowed in production")
    return enabled


def _applies(requirement_scope: list[str], applicability: Mapping[str, Any]) -> bool:
    wanted = applicability.get("applies_to")
    return not wanted or not requirement_scope or bool(set(requirement_scope) & set(wanted))


def snapshot_framework(
    session: Session,
    *,
    organization_id: uuid.UUID,
    framework_key: str,
    scan_id: uuid.UUID,
    control_results: Iterable[ControlResult],
    scope_id: uuid.UUID | None = None,
    applicability: Mapping[str, Any] | None = None,
    supersedes_id: uuid.UUID | None = None,
) -> uuid.UUID | None:
    """Insert one snapshot; None if the framework is not scoreable. Idempotent per scan."""
    level = session.execute(text("SHOW transaction_isolation")).scalar()
    if level not in ("repeatable read", "serializable"):
        raise RuntimeError("scoring needs REPEATABLE READ so a catalog load cannot mix versions")
    applicability = dict(applicability or {})
    framework = session.execute(
        select(Framework).where(Framework.key == framework_key, Framework.retired_at.is_(None))
    ).scalar()
    if framework is None or (framework.status != "released" and not include_drafts()):
        return None
    requirements = [
        r
        for r in session.execute(
            select(Requirement).where(
                Requirement.framework_key == framework_key, Requirement.retired_at.is_(None)
            )
        ).scalars()
        if _applies(r.applies_to, applicability)
    ]
    codes = {r.code for r in requirements}
    mappings = [
        CoreMapping(framework_key, code, control)
        for code, control in session.execute(
            select(MappingRow.requirement_code, MappingRow.control_key)
            .join(Control, Control.key == MappingRow.control_key)
            .where(
                MappingRow.framework_key == framework_key,
                MappingRow.retired_at.is_(None),
                Control.retired_at.is_(None),
            )
        ).all()
        if code in codes
    ]
    results = framework_results(framework_key, codes, mappings, control_results)
    counts = Counter(r.status for r in results)
    keys = framework.attributes.get("score_groups", [])
    value = score(results)
    statement = (
        insert(ScoreSnapshot)
        .values(
            id=uuid.uuid4(),
            organization_id=organization_id,
            framework_key=framework_key,
            framework_version=framework.version,
            catalog_version=framework.catalog_version or "unloaded",
            scan_id=scan_id,
            scope_id=scope_id,
            applicability=applicability,
            score=None if value is None else Decimal(str(value)),
            passed=counts[Status.PASS],
            failed=counts[Status.FAIL],
            manual=counts[Status.MANUAL],
            not_applicable=counts[Status.NOT_APPLICABLE],
            requirement_results={r.control_id: r.status.value for r in results},
            group_scores=group_scores(results, {r.code: r.attributes for r in requirements}, keys),
            supersedes_id=supersedes_id,
        )
        .on_conflict_do_nothing(
            index_elements=["organization_id", "framework_key", "scan_id", "scope_id"],
            index_where=text("supersedes_id IS NULL"),
        )
        .returning(ScoreSnapshot.id)
    )
    created = session.execute(statement).scalar()
    if created is not None or supersedes_id is not None:
        return created
    return session.execute(  # retried job: return the original
        select(ScoreSnapshot.id).where(
            ScoreSnapshot.framework_key == framework_key,
            ScoreSnapshot.scan_id == scan_id,
            ScoreSnapshot.scope_id.is_not_distinct_from(scope_id),
            ScoreSnapshot.supersedes_id.is_(None),
        )
    ).scalar_one()


def control_is_active(session: Session, control_key: str) -> bool:
    """For other modules that reference a control key without a cross-module FK (ADR-008)."""
    query = select(Control.key).where(Control.key == control_key, Control.retired_at.is_(None))
    return session.execute(query).scalar() is not None
