"""Job definitions. Arguments are ids only: queue tables have no RLS (ADR-012 amendment 2)."""

from procrastinate import Blueprint, JobContext


async def retry_stalled_jobs(context: JobContext, timestamp: int) -> None:
    """Retry jobs whose worker stopped sending heartbeats (scanner-connectors spec)."""
    manager = context.app.job_manager
    for job in await manager.get_stalled_jobs():
        await manager.retry_job(job)


def make_blueprint() -> Blueprint:
    """A fresh blueprint per app: Procrastinate renames task objects when an app adds them.

    Task names are explicit, so the task_name stored with each job never depends on the
    module path.
    """
    blueprint = Blueprint()
    task = blueprint.task(name="retry_stalled_jobs", queue="maintenance", pass_context=True)
    blueprint.periodic(cron="*/5 * * * *")(task(retry_stalled_jobs))
    return blueprint
