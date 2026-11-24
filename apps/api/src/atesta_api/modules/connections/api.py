"""Public interface of the connections module.

No API or worker process ever reads a connector secret; connections hold references only.
"""

import httpx
from fastapi import FastAPI

from atesta_api.modules.connections.entra import EntraSettings, EntraSignIn
from atesta_api.modules.connections.m365 import api_router as m365_api_router
from atesta_api.modules.connections.m365 import auth_router as m365_auth_router
from atesta_api.modules.connections.routes import router
from atesta_api.modules.connections.service import (
    ConnectionStateError,
    GoogleServiceAccounts,
    ScanTarget,
    active_connection_ids,
    begin_verification,
    create_connection,
    disconnect_connection,
    ended_connection_ids,
    get_connection,
    google_propagation_open,
    inactive_connection_count,
    list_connections,
    register_google_client,
    scan_target,
)
from atesta_api.modules.connections.verification import (
    TenantMismatchError,
    VerificationReport,
    record_verification,
)


def install_connections(app: FastAPI) -> None:
    """Connection endpoints and the M365 onboarding callbacks (#314)."""
    app.include_router(router)
    app.include_router(m365_api_router)
    app.include_router(m365_auth_router)


def wire_connections(app: FastAPI, client: httpx.Client) -> None:
    """Entra sign-in when both apps are registered here; otherwise onboarding answers 503."""
    settings = EntraSettings.from_env()
    app.state.m365 = None if settings is None else EntraSignIn(settings, client)


__all__ = [
    "ConnectionStateError",
    "GoogleServiceAccounts",
    "ScanTarget",
    "TenantMismatchError",
    "VerificationReport",
    "active_connection_ids",
    "inactive_connection_count",
    "begin_verification",
    "ended_connection_ids",
    "create_connection",
    "disconnect_connection",
    "get_connection",
    "google_propagation_open",
    "install_connections",
    "list_connections",
    "record_verification",
    "register_google_client",
    "router",
    "scan_target",
    "wire_connections",
]
