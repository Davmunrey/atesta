"""FastAPI entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from atesta_api.modules.compliance.api import include_drafts, install_compliance
from atesta_api.modules.connections.api import router as connections_router
from atesta_api.modules.evidence.api import install_evidence
from atesta_api.modules.identity.api import install_identity, wire_identity
from atesta_api.platform import db
from atesta_api.platform.errors import install_error_handlers
from atesta_api.platform.guard import assert_safe_runtime_role
from atesta_api.platform.headers import install_response_headers


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure the database and Cognito; refuse to start on unsafe config or DB role."""
    include_drafts()  # raises on ATESTA_CATALOG_INCLUDE_DRAFTS outside a dev ATESTA_ENV
    sslmode = os.environ.get("ATESTA_DB_SSLMODE", "verify-full")
    engine = db.make_engine(os.environ["ATESTA_DATABASE_URL"], sslmode=sslmode)
    assert_safe_runtime_role(engine, require_tls=sslmode != "disable")
    db.configure(engine)
    with httpx.Client() as client:
        wire_identity(app, client)
        yield
    engine.dispose()


def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    """A fresh app; the contract export uses its own so test-only routes never leak into it."""
    created = FastAPI(title="Atesta API", version="0.0.0", lifespan=lifespan)
    install_error_handlers(created)
    install_response_headers(created)
    install_identity(created)
    install_compliance(created)
    install_evidence(created)
    created.include_router(connections_router)
    created.add_api_route("/health", health, methods=["GET"])
    return created


app = create_app()
