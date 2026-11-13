"""get_db reaches handlers only through DbSession (function scope). Any other scope or form
opens a second session without the tenant context (tenant-data-layer spec)."""

from collections.abc import Callable
from typing import Annotated, Any

import pytest
from atesta_api.main import app
from atesta_api.platform import db
from atesta_api.platform.db import DbSession, get_db
from fastapi import APIRouter, Depends, FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts
from sqlalchemy.orm import Session


def get_db_scopes(application: FastAPI) -> list[str | None]:
    """Scopes of every get_db dependant on the effective routes, router dependencies included."""
    scopes: list[str | None] = []

    def walk(dependant: Dependant) -> None:
        if dependant.call is get_db:
            scopes.append(dependant.scope)
        for sub in dependant.dependencies:
            walk(sub)

    for context in iter_route_contexts(application.routes):
        if isinstance(context.original_route, APIRoute):
            walk(context.dependant)  # effective: include_router dependencies merged in
    return scopes


def test_app_uses_get_db_only_through_dbsession() -> None:
    scopes = get_db_scopes(app)
    assert scopes, "no get_db dependant found: the walk is vacuous"
    assert set(scopes) == {"function"}


alias = get_db
SECOND_SESSION: dict[str, Any] = {
    "bare Depends": Depends(get_db),
    "request scope": Depends(get_db, scope="request"),
    "qualified name": Depends(db.get_db, scope="request"),
    "keyword form": Depends(dependency=get_db),
    "aliased import": Depends(alias),
}


def _app(route: Callable[[APIRouter], None], **include: Any) -> FastAPI:
    router = APIRouter()
    route(router)
    application = FastAPI()
    application.include_router(router, **include)
    return application


@pytest.mark.parametrize("form", sorted(SECOND_SESSION))
def test_walk_flags_a_second_session(form: str) -> None:
    def route(router: APIRouter) -> None:
        @router.get("/x")
        def handler(s: DbSession, other: Annotated[Session, SECOND_SESSION[form]]) -> None: ...

    assert set(get_db_scopes(_app(route))) != {"function"}


def test_walk_sees_router_level_dependencies() -> None:
    def route(router: APIRouter) -> None:
        @router.get("/x")
        def handler(s: DbSession) -> None: ...

    flagged = _app(route, dependencies=[Depends(get_db, scope="request")])
    assert set(get_db_scopes(flagged)) != {"function"}
