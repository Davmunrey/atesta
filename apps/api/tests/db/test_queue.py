"""Procrastinate queue on the real database: grants, ids-only rows, jobs in org context."""

import asyncio
import uuid

from atesta_worker import context
from atesta_worker.app import build_app
from procrastinate import Blueprint
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from .conftest import APP_PASSWORD, ORG_A, ORG_B

QUEUE_TABLES = (
    "procrastinate_jobs",
    "procrastinate_events",
    "procrastinate_periodic_defers",
    "procrastinate_workers",
)


def test_queue_tables_have_no_rls_and_functions_are_not_public(superuser: Engine) -> None:
    with superuser.connect() as conn:
        rls = conn.execute(
            text("SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(:t)"),
            {"t": list(QUEUE_TABLES)},
        ).all()
        functions = conn.execute(
            text(
                "SELECT p.proname, p.prosecdef,"
                " has_function_privilege('atesta_app', p.oid, 'EXECUTE'),"
                " EXISTS (SELECT 1 FROM aclexplode(p.proacl) x WHERE x.grantee = 0)"
                " FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace"
                " AND p.proname LIKE 'procrastinate\\_%'"
            )
        ).all()
    assert sorted(r[0] for r in rls) == sorted(QUEUE_TABLES)
    assert not any(r[1] for r in rls)
    assert len(functions) >= 10
    assert [f for f in functions if f[1] or not f[2] or f[3]] == []


def _app_url(database: URL) -> URL:
    return database.set(username="atesta_app", password=APP_PASSWORD)


def test_worker_runs_jobs_in_their_own_org_context(
    database: URL, app_engine: Engine, superuser: Engine, probe: dict[uuid.UUID, uuid.UUID]
) -> None:
    seen: list[tuple[str, list[str], bool]] = []
    jobs = Blueprint()

    @jobs.task(name="read_probe", queue="test")
    def read_probe(organization_id: str, probe_id: str) -> None:
        with context.org_session(organization_id) as session:
            values = session.execute(text("SELECT v FROM probe ORDER BY v")).scalars().all()
            found = session.execute(
                text("SELECT 1 FROM probe WHERE id = :i"), {"i": uuid.UUID(probe_id)}
            ).first()
        seen.append((organization_id, list(values), found is not None))

    context.configure(app_engine)
    app = build_app(_app_url(database), "disable", extra=(jobs,))
    task = app.tasks["atesta1:read_probe"]

    async def run() -> None:
        async with app.open_async():
            await task.defer_async(organization_id=str(ORG_A), probe_id=str(probe[ORG_A]))
            # Org B's job names org A's row: RLS hides it, the job still succeeds empty-handed.
            await task.defer_async(organization_id=str(ORG_B), probe_id=str(probe[ORG_A]))
            await app.run_worker_async(queues=["test"], wait=False)

    asyncio.run(run())

    assert seen == [(str(ORG_A), ["a"], True), (str(ORG_B), ["b"], False)]
    with superuser.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT args, status::text FROM procrastinate_jobs"
                " WHERE task_name = 'atesta1:read_probe' ORDER BY id"
            )
        ).all()
        conn.execute(text("DELETE FROM procrastinate_jobs WHERE queue_name = 'test'"))
    assert [set(args) for args, _ in rows] == [{"organization_id", "probe_id"}] * 2
    assert [status for _, status in rows] == ["succeeded", "succeeded"]
