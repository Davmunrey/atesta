"""FastAPI entry point."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from atesta_api.modules.identity.api import router as identity_router
from atesta_api.modules.identity.api import wire_identity
from atesta_api.platform import db
from atesta_api.platform.guard import assert_safe_runtime_role


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure the database and Cognito; refuse to start on an unsafe DB role."""
    sslmode = os.environ.get("ATESTA_DB_SSLMODE", "verify-full")
    engine = db.make_engine(
        os.environ["ATESTA_DATABASE_URL"],
        sslmode=sslmode,
        sslrootcert=os.environ.get("ATESTA_DB_SSLROOTCERT"),
    )
    assert_safe_runtime_role(engine, require_tls=sslmode != "disable")
    db.configure(engine)
    with httpx.Client() as client:
        wire_identity(app, client)
        yield
    engine.dispose()


app = FastAPI(title="Atesta API", version="0.0.0", lifespan=lifespan)
app.include_router(identity_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
