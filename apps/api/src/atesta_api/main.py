"""FastAPI entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

import httpx
from fastapi import FastAPI

from atesta_api.modules.compliance.api import include_drafts, install_compliance
from atesta_api.modules.connections.api import install_connections, wire_connections
from atesta_api.modules.evidence.api import install_evidence
from atesta_api.modules.identity.api import install_identity, wire_identity
from atesta_api.modules.scanning.api import router as scanning_router
from atesta_api.platform import db
from atesta_api.platform.errors import install_error_handlers
from atesta_api.platform.guard import assert_safe_runtime_role
from atesta_api.platform.headers import install_response_headers
from atesta_api.platform.logs import install_log_redaction


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
        wire_connections(app, client)
        async with AsyncExitStack() as stack:
            if run_mcp := getattr(app.state, "mcp_session_manager", None):
                await stack.enter_async_context(run_mcp())
            yield
    engine.dispose()


def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    """A fresh app; the contract export uses its own so test-only routes never leak into it."""
    install_log_redaction()  # uvicorn logs unhandled errors with exc_info (rule 2)
    created = FastAPI(title="Atesta API", version="0.0.0", lifespan=lifespan)
    install_error_handlers(created)
    install_response_headers(created)
    install_identity(created)
    install_compliance(created)
    install_evidence(created)
    install_connections(created)
    created.include_router(scanning_router)
    created.add_api_route("/health", health, methods=["GET"])
    if os.environ.get("ATESTA_MCP_REMOTE") == "1":
        mount_remote_mcp(created)
    return created


def mount_remote_mcp(app: FastAPI) -> None:
    """The hosted MCP server at /mcp (ADR-016), off unless ATESTA_MCP_REMOTE=1. Its tools call
    this same app in-process with the caller's key, so every rule of the API applies."""
    from atesta_mcp.remote import remote_app

    hosts = [h.strip() for h in os.environ.get("ATESTA_MCP_ALLOWED_HOSTS", "").split(",")]
    origin = os.environ.get("ATESTA_WEB_ORIGIN", "").rstrip("/")
    gated, run = remote_app(app, [h for h in hosts if h], [origin] if origin else [])
    app.mount("/mcp", gated)
    app.state.mcp_session_manager = run


app = create_app()
