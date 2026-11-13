"""Score snapshots from DB rows (control-model spec test plan). Synthetic packs only."""

import uuid
from collections.abc import Iterator

import pytest
from atesta_api.modules.compliance.api import snapshot_framework
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_core.scoring import ControlResult, Status
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

CATALOG = """
INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes, status,
  attributes, catalog_version) VALUES
 ('fw_x', 'X', '1', 'EU', 'src', 'test', 'released', '{}', 'r1'),
 ('fw_y', 'Y', '2', 'EU', 'src', 'test', 'released', '{"score_groups": ["dim"]}', 'r1'),
 ('fw_d', 'D', '1', 'EU', 'src', 'test', 'draft', '{}', 'r1');
INSERT INTO controls (key, title_es, title_en, description_es, description_en, retired_at) VALUES
 ('c1', 't', 't', 'd', 'd', NULL), ('c2', 't', 't', 'd', 'd', NULL),
 ('c3', 't', 't', 'd', 'd', NULL), ('c4', 't', 't', 'd', 'd', NULL),
 ('c_old', 't', 't', 'd', 'd', now());
INSERT INTO requirements (framework_key, code, title_es, source, applies_to, attributes,
  retired_at) VALUES
 ('fw_x', 'X-1', 't', 's', '{}', '{}', NULL), ('fw_x', 'X-2', 't', 's', '{high}', '{}', NULL),
 ('fw_x', 'X-3', 't', 's', '{}', '{}', now()),
 ('fw_y', 'Y-1', 't', 's', '{}', '{"dim": "a"}', NULL),
 ('fw_y', 'Y-2', 't', 's', '{}', '{"dim": "b"}', NULL),
 ('fw_d', 'D-1', 't', 's', '{}', '{}', NULL);
INSERT INTO mappings (framework_key, requirement_code, control_key, rationale, source,
  retired_at) VALUES
 ('fw_x', 'X-1', 'c1', 'r', 's', NULL), ('fw_x', 'X-1', 'c4', 'r', 's', now()),
 ('fw_x', 'X-1', 'c_old', 'r', 's', NULL),
 ('fw_x', 'X-2', 'c2', 'r', 's', NULL), ('fw_x', 'X-3', 'c2', 'r', 's', NULL),
 ('fw_y', 'Y-1', 'c1', 'r', 's', NULL), ('fw_y', 'Y-1', 'c3', 'r', 's', NULL),
 ('fw_y', 'Y-2', 'c2', 'r', 's', NULL), ('fw_d', 'D-1', 'c1', 'r', 's', NULL);
"""
RESULTS = [
    ControlResult("c1", Status.PASS),
    ControlResult("c2", Status.FAIL),
    ControlResult("c3", Status.PASS),
]


@pytest.fixture(scope="module", autouse=True)
def catalog(superuser: Engine, probe: object) -> None:
    with superuser.begin() as conn:
        conn.exec_driver_sql(CATALOG)


@pytest.fixture
def tx(app_engine: Engine, probe: object) -> Iterator[Session]:
    """REPEATABLE READ transaction in org A's context, rolled back at the end."""
    with app_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        enter_org_context(session, ORG_A, ContextReason.JOB)
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


def snap(
    session: Session, key: str, scan: uuid.UUID | None = None, **kw: object
) -> uuid.UUID | None:
    return snapshot_framework(
        session,
        organization_id=ORG_A,
        framework_key=key,
        scan_id=scan or uuid.uuid4(),
        control_results=RESULTS,
        **kw,  # type: ignore[arg-type]
    )


def row(session: Session, snapshot_id: uuid.UUID | None) -> dict[str, object]:
    query = text("SELECT * FROM score_snapshots WHERE id = :i")
    return dict(session.execute(query, {"i": snapshot_id}).mappings().one())


def test_one_scan_scores_every_framework(tx: Session) -> None:
    scan = uuid.uuid4()
    x, y = row(tx, snap(tx, "fw_x", scan)), row(tx, snap(tx, "fw_y", scan))
    assert (float(x["score"]), x["requirement_results"]) == (50.0, {"X-1": "pass", "X-2": "fail"})
    assert (float(y["score"]), y["group_scores"]) == (50.0, {"dim": {"a": 100.0, "b": 0.0}})
    assert (x["framework_version"], x["catalog_version"]) == ("1", "r1")


def test_retired_rows_and_applicability(tx: Session) -> None:
    low = row(tx, snap(tx, "fw_x", applicability={"applies_to": ["low"]}))
    assert low["requirement_results"] == {"X-1": "pass"}  # X-2 out of scope, X-3 retired
    # X-1 has a retired mapping to active c4 (no result) and an active mapping to retired c_old
    # (no result): each filter alone keeps X-1 from turning manual.
    assert float(low["score"]) == 100.0
    assert low["manual"] == 0


def test_draft_framework_is_not_scored(tx: Session) -> None:
    assert snap(tx, "fw_d") is None


def test_draft_framework_is_scored_with_the_flag_in_dev(
    tx: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    monkeypatch.setenv("ATESTA_ENV", "test")
    assert row(tx, snap(tx, "fw_d"))["requirement_results"] == {"D-1": "pass"}


def test_retried_job_is_idempotent_and_corrections_supersede(tx: Session) -> None:
    scan = uuid.uuid4()
    first = snap(tx, "fw_x", scan)
    assert snap(tx, "fw_x", scan) == first
    correction = snap(tx, "fw_x", scan, supersedes_id=first)
    assert correction not in (None, first)
    count = text("SELECT count(*) FROM score_snapshots WHERE scan_id = :s")
    assert tx.execute(count, {"s": scan}).scalar_one() == 2


LIVE = text(  # what trend and diff read: rows nothing supersedes
    "SELECT s.id FROM score_snapshots s WHERE s.framework_key = :f AND s.scan_id = :s"
    " AND NOT EXISTS (SELECT 1 FROM score_snapshots n WHERE n.supersedes_id = s.id)"
)


def test_retried_correction_is_idempotent_and_trend_reads_only_it(tx: Session) -> None:
    scan = uuid.uuid4()
    first = snap(tx, "fw_x", scan)
    correction = snap(tx, "fw_x", scan, supersedes_id=first)
    assert snap(tx, "fw_x", scan, supersedes_id=first) == correction
    assert tx.execute(LIVE, {"f": "fw_x", "s": scan}).scalars().all() == [correction]
    second = snap(tx, "fw_x", scan, supersedes_id=correction)  # the chain stays linear
    assert tx.execute(LIVE, {"f": "fw_x", "s": scan}).scalars().all() == [second]


@pytest.mark.parametrize("other", ["framework", "scan", "scope"])
def test_correction_supersedes_only_its_own_framework_scan_and_scope(
    tx: Session, other: str
) -> None:
    scan, scope = uuid.uuid4(), uuid.uuid4()
    original = snap(tx, "fw_x", scan, scope_id=scope)
    kwargs: dict[str, object] = {"scope_id": scope, "supersedes_id": original}
    key = "fw_y" if other == "framework" else "fw_x"
    target_scan = uuid.uuid4() if other == "scan" else scan
    if other == "scope":
        kwargs["scope_id"] = None  # NULL scope must not skip the lineage check
    with pytest.raises(IntegrityError, match="lineage"), tx.begin_nested():
        snap(tx, key, target_scan, **kwargs)


def test_requires_repeatable_read(db_rollback: Session) -> None:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    with pytest.raises(RuntimeError, match="REPEATABLE READ"):
        snap(db_rollback, "fw_x")


@pytest.mark.parametrize(
    "statement", ["UPDATE score_snapshots SET score = 1", "DELETE FROM score_snapshots"]
)
def test_append_only_and_isolated(tx: Session, statement: str) -> None:
    snap(tx, "fw_x")
    with pytest.raises(DBAPIError, match="permission denied"), tx.begin_nested():
        tx.execute(text(statement))
    with pytest.raises(DBAPIError, match="row-level security"):
        snapshot_framework(
            tx,
            organization_id=ORG_B,
            framework_key="fw_x",
            scan_id=uuid.uuid4(),
            control_results=[],
        )
