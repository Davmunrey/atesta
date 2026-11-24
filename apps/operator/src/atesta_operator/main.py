"""Operator API entry point (ADR-017, option B): its own process, image, database role and staff
pool. Startup refuses a staff pool without required MFA and any database role but
`atesta_operator` (ADR-012 amendment 8, "Startup guard")."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from atesta_api.modules.identity.api import (
    CognitoOAuth,
    SessionCrypto,
    TokenVerifier,
    jwks_fetcher,
)
from atesta_api.platform import db
from atesta_api.platform.errors import install_error_handlers
from atesta_api.platform.guard import assert_safe_runtime_role
from atesta_api.platform.headers import install_response_headers
from atesta_api.platform.logs import install_log_redaction
from fastapi import FastAPI
from sqlalchemy import Engine

from atesta_operator import me, organizations, session
from atesta_operator.mfa import MfaConfigReader, assert_staff_pool_requires_mfa
from atesta_operator.settings import Settings

OPERATOR_ROLE = "atesta_operator"


def startup(settings: Settings, read_mfa: MfaConfigReader | None = None) -> Engine:
    """The checks that refuse to start, then the session factory. Returns the engine."""
    assert_staff_pool_requires_mfa(settings, read_mfa)
    engine = db.make_engine(settings.database_url, sslmode=settings.sslmode)
    try:
        assert_safe_runtime_role(
            engine, require_tls=settings.sslmode != "disable", role=OPERATOR_ROLE
        )
    except RuntimeError:
        engine.dispose()
        raise
    db.configure(engine)
    return engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    engine = startup(settings)
    with httpx.Client() as client:
        verifier = TokenVerifier(settings.cognito, jwks_fetcher(settings.cognito, client))
        app.state.token_verifier = verifier
        app.state.web_origin = settings.web_origin
        app.state.session_crypto = SessionCrypto(settings.session_key)
        app.state.oauth = CognitoOAuth(settings.cognito, client, verifier, settings.web_origin)
        yield
    engine.dispose()


def health() -> dict[str, str]:
    return {"status": "ok"}


def create_app() -> FastAPI:
    install_log_redaction()  # rule 2: no exception text or query string in any log record
    created = FastAPI(title="Atesta operator API", version="0.0.0", lifespan=lifespan)
    install_error_handlers(created)
    install_response_headers(created)
    created.add_exception_handler(session.SessionEndedError, session.session_ended_handler)
    created.include_router(session.router)
    created.include_router(me.router)
    created.include_router(organizations.router)
    created.add_api_route("/health", health, methods=["GET"])
    return created


app = create_app()
