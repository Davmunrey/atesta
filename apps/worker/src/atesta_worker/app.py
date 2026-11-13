"""The Procrastinate app (ADR-003): Postgres queue, TLS as in the API, ids-only arguments."""

import inspect
import typing
from collections.abc import Iterable
from typing import Any

from atesta_api.platform.db import RDS_CA, SSLMODES
from procrastinate import App, Blueprint, PsycopgConnector
from sqlalchemy.engine import URL, make_url

from atesta_worker.jobs import make_blueprint

# Procrastinate passes these itself: the job context and a periodic job's schedule time.
_INJECTED = {"context": object, "timestamp": int}


def conninfo(url: str | URL) -> str:
    """libpq URL for psycopg. TLS settings never come from the URL (as in make_engine)."""
    clean = make_url(url).difference_update_query(["sslmode", "sslrootcert"])
    return clean.set(drivername="postgresql").render_as_string(hide_password=False)


def connection_kwargs(sslmode: str) -> dict[str, Any]:
    if sslmode not in SSLMODES:
        raise ValueError(f"sslmode must be one of {sorted(SSLMODES)}, got {sslmode!r}")
    kwargs: dict[str, Any] = {"sslmode": sslmode}
    if sslmode == "verify-full":
        kwargs["sslrootcert"] = RDS_CA
    return kwargs


def non_id_parameters(tasks: Iterable[Any]) -> list[str]:
    """Task parameters that are not `<name>_id: str`, besides the ones Procrastinate injects.

    Job arguments land in procrastinate_jobs, which every atesta_app session can read, so they
    must never hold names, emails, tokens or document text (ADR-012 amendment 2).
    """
    bad: list[str] = []
    for task in tasks:
        hints = typing.get_type_hints(task.func)
        for name in inspect.signature(task.func).parameters:
            kind = hints.get(name)
            injected = name in _INJECTED and (name == "context" or kind is int)
            if not injected and not (name.endswith("_id") and kind is str):
                bad.append(f"{task.name}({name})")
    return bad


def make_connector(url: str | URL, sslmode: str) -> PsycopgConnector:
    return PsycopgConnector(conninfo=conninfo(url), kwargs=connection_kwargs(sslmode))


def build_app(url: str | URL, sslmode: str, extra: Iterable[Blueprint] = ()) -> App:
    """The worker's app. Refuses to start if any Atesta task takes a non-id argument.

    Procrastinate's own builtin tasks are not checked: Atesta never defers them.
    """
    blueprints = [make_blueprint(), *extra]
    bad = non_id_parameters(t for bp in blueprints for t in bp.tasks.values())
    if bad:
        raise ValueError(f"job arguments must be ids only: {', '.join(sorted(bad))}")
    app = App(connector=make_connector(url, sslmode))
    for index, source in enumerate(blueprints):
        app.add_tasks_from(source, namespace="atesta" if index == 0 else f"atesta{index}")
    return app
