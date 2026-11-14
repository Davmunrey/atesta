"""Score snapshots from active catalog rows (control-model spec). Scoring logic stays in core."""

import os
import uuid
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from atesta_core.frameworks import Mapping as CoreMapping
from atesta_core.frameworks import framework_results, group_scores
from atesta_core.scoring import ControlResult, Status, score
from sqlalchemy import ColumnElement, and_, or_, select, text
from sqlalchemy.dialects.postgresql import distinct_on, insert
from sqlalchemy.orm import Session, aliased

from atesta_api.modules.compliance.models import (
    Check,
    Control,
    ControlCheck,
    ControlReview,
    Framework,
    Requirement,
    ScoreSnapshot,
)
from atesta_api.modules.compliance.models import (
    Mapping as MappingRow,
)

_DRAFT_ENVS = frozenset({"local", "dev", "test"})


def include_drafts() -> bool:
    """Dev may score draft packs (rule 10). Fails closed: the flag needs an explicit dev ATESTA_ENV.

    Called first at startup and again before scoring, for processes that skip the API lifespan.
    """
    if os.environ.get("ATESTA_CATALOG_INCLUDE_DRAFTS") != "true":
        return False
    if os.environ.get("ATESTA_ENV") not in _DRAFT_ENVS:
        raise RuntimeError(
            "ATESTA_CATALOG_INCLUDE_DRAFTS=true requires ATESTA_ENV in "
            + "/".join(sorted(_DRAFT_ENVS))
        )
    return True


def _scoreable() -> ColumnElement[bool]:
    """Visibility gate: drafts need explicit development access."""
    active = Framework.retired_at.is_(None)
    return active if include_drafts() else and_(active, Framework.status == "released")


def _assessable() -> ColumnElement[bool]:
    """Preparation content stays readable without letting scans create assessments."""
    return and_(
        _scoreable(),
        or_(
            ~Framework.attributes.has_key("assessment_enabled"),
            Framework.attributes.contains({"assessment_enabled": True}),
        ),
    )


@dataclass(frozen=True, slots=True)
class FrameworkInfo:
    key: str
    name: str
    version: str
    status: str
    catalog_version: str | None


def active_frameworks(session: Session) -> list[FrameworkInfo]:
    """Frameworks a customer may see, select or be scored on."""
    rows = session.execute(select(Framework).where(_scoreable()).order_by(Framework.key))
    return [
        FrameworkInfo(f.key, f.name, f.version, f.status, f.catalog_version) for f in rows.scalars()
    ]


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
        select(Framework).where(Framework.key == framework_key, _assessable())
    ).scalar()
    if framework is None:
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
    row = insert(ScoreSnapshot).values(
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
    if supersedes_id is None:  # one original per (framework, scan, scope)
        statement = row.on_conflict_do_nothing(
            index_elements=["organization_id", "framework_key", "scan_id", "scope_id"],
            index_where=text("supersedes_id IS NULL"),
        )
        existing = select(ScoreSnapshot.id).where(
            ScoreSnapshot.framework_key == framework_key,
            ScoreSnapshot.scan_id == scan_id,
            ScoreSnapshot.scope_id.is_not_distinct_from(scope_id),
            ScoreSnapshot.supersedes_id.is_(None),
        )
    else:  # one correction per snapshot; the lineage FK keeps it in the same framework and scan
        statement = row.on_conflict_do_nothing(
            index_elements=["organization_id", "supersedes_id"],
            index_where=text("supersedes_id IS NOT NULL"),
        )
        existing = select(ScoreSnapshot.id).where(ScoreSnapshot.supersedes_id == supersedes_id)
    created = session.execute(statement.returning(ScoreSnapshot.id)).scalar()
    if created is not None:
        return created
    earlier: uuid.UUID = session.execute(existing).scalar_one()  # retried job
    return earlier


def control_is_active(session: Session, control_key: str) -> bool:
    """For other modules that reference a control key without a cross-module FK (ADR-008)."""
    query = select(Control.key).where(Control.key == control_key, Control.retired_at.is_(None))
    return session.execute(query).scalar() is not None


def scoreable_framework_keys(session: Session) -> list[str]:
    """Keys snapshot_scores scores, excluding visible preparation-only packs."""
    return list(session.execute(select(Framework.key).where(_assessable())).scalars())


def active_control_checks(session: Session) -> dict[str, list[tuple[str, str]]]:
    """Automated controls and their checks (engine, check_id), active catalog rows only."""
    rows = session.execute(
        select(ControlCheck.control_key, ControlCheck.engine, ControlCheck.check_id)
        .join(Control, Control.key == ControlCheck.control_key)
        .join(
            Check,
            and_(Check.engine == ControlCheck.engine, Check.check_id == ControlCheck.check_id),
        )
        .where(
            ControlCheck.retired_at.is_(None),
            Control.retired_at.is_(None),
            Control.manual.is_(False),
            Check.retired_at.is_(None),
        )
        .order_by(ControlCheck.control_key, ControlCheck.engine, ControlCheck.check_id)
    )
    checks: dict[str, list[tuple[str, str]]] = {}
    for control_key, engine, check_id in rows:
        checks.setdefault(control_key, []).append((engine, check_id))
    return checks


def active_control_keys(session: Session, keys: Iterable[str]) -> set[str]:
    """The subset of keys that name active controls, in one query."""
    wanted = set(keys)
    if not wanted:
        return set()
    query = select(Control.key).where(Control.key.in_(wanted), Control.retired_at.is_(None))
    return set(session.execute(query).scalars())


def reviewed_control_results(
    session: Session, organization_id: uuid.UUID, as_of: datetime
) -> list[ControlResult]:
    """Human results of active manual controls as of a moment (manual-control-review spec).

    The latest review recorded no later than as_of decides; if it has expired by then
    (valid_until before as_of's UTC date) the control stays without a result, even when an
    older review would still hold. Automated controls are never taken from a review (ADR-005).
    """
    latest = (
        select(ControlReview.control_key, ControlReview.status, ControlReview.valid_until)
        .join(Control, Control.key == ControlReview.control_key)
        .where(
            ControlReview.organization_id == organization_id,
            ControlReview.reviewed_at <= as_of,
            Control.manual.is_(True),
            Control.retired_at.is_(None),
        )
        .ext(distinct_on(ControlReview.control_key))
        .order_by(
            ControlReview.control_key, ControlReview.reviewed_at.desc(), ControlReview.id.desc()
        )
    )
    day = as_of.astimezone(UTC).date()
    return [
        ControlResult(key, Status(status))
        for key, status, valid_until in session.execute(latest)
        if valid_until >= day
    ]


def snapshot_chain_tip(
    session: Session, organization_id: uuid.UUID, framework_key: str, scan_id: uuid.UUID
) -> uuid.UUID | None:
    """The org-wide snapshot of a scan that nothing supersedes yet: the next correction's parent."""
    newer = aliased(ScoreSnapshot)
    return session.execute(
        select(ScoreSnapshot.id).where(
            ScoreSnapshot.organization_id == organization_id,
            ScoreSnapshot.framework_key == framework_key,
            ScoreSnapshot.scan_id == scan_id,
            ScoreSnapshot.scope_id.is_(None),
            ~select(newer.id).where(newer.supersedes_id == ScoreSnapshot.id).exists(),
        )
    ).scalar()
