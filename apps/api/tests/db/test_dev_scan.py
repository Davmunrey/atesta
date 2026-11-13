"""`atesta-dev-scan` end to end on a real Postgres (scanner-connectors spec, Local development)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from atesta_api.modules.scanning.api import FixtureRunner, LocalScanStore, ScanJob
from atesta_api.platform.db import make_engine
from atesta_worker import context, dev_scan, jobs
from atesta_worker.dev_scan import DEV_ORG, DEV_SCAN, FIXTURES, run
from sqlalchemy import text
from sqlalchemy.engine import URL

from .conftest import APP_PASSWORD, fresh_database

SNAPSHOTS = text(
    "SELECT framework_key, count(*), min(score), min(requirement_results::text)"
    " FROM score_snapshots WHERE scan_id = :s AND framework_key LIKE 'syn_%' GROUP BY 1 ORDER BY 1"
)


@pytest.fixture(scope="module")
def own_database() -> Iterator[URL]:
    """Its own database: the synthetic catalog is global and must not meet other modules'."""
    with fresh_database() as url:
        yield url


@pytest.fixture
def dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATESTA_ENV", "test")
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")


@pytest.mark.usefixtures("dev")
def test_one_fixture_scan_gives_one_snapshot_per_synthetic_framework(
    own_database: URL, tmp_path: Path
) -> None:
    app_url = own_database.set(username="atesta_app", password=APP_PASSWORD)
    # A crashed earlier run left write-once outputs and no scan row: they are reused.
    FixtureRunner(LocalScanStore(tmp_path), FIXTURES).run(ScanJob(DEV_ORG, DEV_SCAN, 1, "m365"))
    first = run(own_database, app_url, "disable", tmp_path)
    assert run(own_database, app_url, "disable", tmp_path) == first  # rerun: same snapshots
    assert first.keys() == {"syn_alpha", "syn_beta"}  # the only frameworks in this database
    # The deferred job scores the same scan again: nothing new, at REPEATABLE READ.
    context.configure(make_engine(app_url, sslmode="disable", null_pool=True))
    jobs.snapshot_scores(str(DEV_ORG), str(DEV_SCAN))
    with make_engine(own_database, sslmode="disable", null_pool=True).connect() as conn:
        rows = [tuple(r) for r in conn.execute(SNAPSHOTS, {"s": DEV_SCAN})]
        manual = text("SELECT key FROM controls WHERE key LIKE 'syn.%' AND manual ORDER BY key")
        assert conn.execute(manual).scalars().all() == ["syn.paper"]  # no checks: manual
        drafts = text("SELECT key FROM frameworks WHERE status = 'draft' ORDER BY key")
        assert conn.execute(drafts).scalars().all() == ["syn_alpha", "syn_beta"]  # never released
    alpha = '{"A-1": "pass", "A-2": "fail", "A-3": "manual"}'
    beta = '{"B-1": "manual", "B-2": "manual", "B-3": "manual"}'
    assert [(k, n, None if s is None else float(s), r) for k, n, s, r in rows] == [
        ("syn_alpha", 1, 50.0, alpha),
        ("syn_beta", 1, None, beta),  # Google check out of scope, manual control: unassessed
    ]


@pytest.mark.usefixtures("dev")
def test_a_framework_without_a_snapshot_fails_the_run(
    own_database: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_url = own_database.set(username="atesta_app", password=APP_PASSWORD)
    monkeypatch.setattr(dev_scan, "snapshot_scores", lambda session, scan_id: {})
    with pytest.raises(RuntimeError, match="no snapshot for synthetic frameworks: syn_alpha"):
        run(own_database, app_url, "disable", tmp_path)


UNREACHABLE = "postgresql+psycopg://nobody@127.0.0.1:1/none"


@pytest.mark.parametrize("env", ["prod", "staging", ""])
def test_dev_scan_refuses_before_connecting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: str
) -> None:
    monkeypatch.setenv("ATESTA_ENV", env)
    with pytest.raises(RuntimeError, match="ATESTA_ENV"):
        run(UNREACHABLE, UNREACHABLE, "disable", tmp_path)
