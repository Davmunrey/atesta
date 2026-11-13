"""Score snapshots from DB rows (control-model spec test plan). Synthetic packs only."""

import uuid
from collections.abc import Iterator

import pytest
from atesta_api.modules.compliance.api import active_frameworks, snapshot_framework
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from atesta_core.scoring import ControlResult, Status
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

CATALOG = """
INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes, status,
  attributes, catalog_version) VALUES
 ('fw_x', 'X', '1', 'EU', 'src', 'test', 'released', '{}', 'r1'),
 ('fw_y', 'Y', '2', 'EU', 'src', 'test', 'released', '{"score_groups": ["dim"]}', 'r1'),
 ('fw_d', 'D', '1', 'EU', 'src', 'test', 'draft', '{}', 'r1');
INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes, status,
  retired_at) VALUES ('fw_r', 'R', '1', 'EU', 'src', 'test', 'released', now());
INSERT INTO controls (key, title_es, title_en, description_es, description_en, retired_at) VALUES
 ('c1', 't', 't', 'd', 'd', NULL), ('c2', 't', 't', 'd', 'd', NULL),
 ('c3', 't', 't', 'd', 'd', NULL), ('c_old', 't', 't', 'd', 'd', now());
INSERT INTO requirements (framework_key, code, title_es, source, applies_to, attributes,
  retired_at) VALUES
 ('fw_x', 'X-1', 't', 's', '{}', '{}', NULL), ('fw_x', 'X-2', 't', 's', '{high}', '{}', NULL),
 ('fw_x', 'X-3', 't', 's', '{}', '{}', now()),
 ('fw_y', 'Y-1', 't', 's', '{}', '{"dim": "a"}', NULL),
 ('fw_y', 'Y-2', 't', 's', '{}', '{"dim": "b"}', NULL),
 ('fw_d', 'D-1', 't', 's', '{}', '{}', NULL);
INSERT INTO mappings (framework_key, requirement_code, control_key, rationale, source,
  retired_at) VALUES
 ('fw_x', 'X-1', 'c1', 'r', 's', NULL), ('fw_x', 'X-1', 'c_old', 'r', 's', now()),
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
    assert float(low["score"]) == 100.0  # retired mapping to c_old does not make X-1 manual


def test_draft_framework_is_not_scored(tx: Session) -> None:
    assert snap(tx, "fw_d") is None


def test_retried_job_is_idempotent_and_corrections_supersede(tx: Session) -> None:
    scan = uuid.uuid4()
    first = snap(tx, "fw_x", scan)
    assert snap(tx, "fw_x", scan) == first
    correction = snap(tx, "fw_x", scan, supersedes_id=first)
    assert correction not in (None, first)
    count = text("SELECT count(*) FROM score_snapshots WHERE scan_id = :s")
    assert tx.execute(count, {"s": scan}).scalar_one() == 2


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


def test_only_released_active_frameworks_are_listed_and_scored(
    tx: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The listing and scoring share one gate (rule 10 at runtime)."""
    keys = [f.key for f in active_frameworks(tx)]
    assert "fw_x" in keys and "fw_y" in keys
    assert "fw_d" not in keys  # draft
    assert "fw_r" not in keys  # released but retired
    assert snap(tx, "fw_r") is None
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    monkeypatch.setenv("ATESTA_ENV", "test")
    keys = [f.key for f in active_frameworks(tx)]
    assert "fw_d" in keys and "fw_r" not in keys
