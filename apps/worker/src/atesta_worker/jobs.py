"""Job definitions. Arguments are ids only: queue tables have no RLS (ADR-012 amendment 2)."""

import uuid

from atesta_api.modules.scanning.api import snapshot_scores as score_scan
from procrastinate import Blueprint, JobContext, RetryStrategy
from sqlalchemy.exc import OperationalError

from atesta_worker.context import org_session


async def retry_stalled_jobs(context: JobContext, timestamp: int) -> None:
    """Retry jobs whose worker stopped sending heartbeats (scanner-connectors spec)."""
    manager = context.app.job_manager
    for job in await manager.get_stalled_jobs():
        await manager.retry_job(job)


def snapshot_scores(organization_id: str, scan_id: str) -> None:
    """One snapshot per scoreable framework for an ingested scan. Idempotent per scan."""
    with org_session(organization_id, isolation_level="REPEATABLE READ") as session:
        score_scan(session, uuid.UUID(scan_id))


def make_blueprint() -> Blueprint:
    """A fresh blueprint per app: Procrastinate renames task objects when an app adds them.

    Task names are explicit, so the task_name stored with each job never depends on the
    module path.
    """
    blueprint = Blueprint()
    task = blueprint.task(name="retry_stalled_jobs", queue="maintenance", pass_context=True)
    blueprint.periodic(cron="*/5 * * * *")(task(retry_stalled_jobs))
    # Transient database errors only (serialization failures, lost connections). A scan the
    # ids do not find is never retried.
    transient = RetryStrategy(max_attempts=3, retry_exceptions={OperationalError})
    blueprint.task(name="snapshot_scores", queue="scans", retry=transient)(snapshot_scores)
    return blueprint
