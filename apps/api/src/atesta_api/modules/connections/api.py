"""Public interface of the connections module.

No API or worker process ever reads a connector secret; connections hold references only.
"""

from atesta_api.modules.connections.routes import router
from atesta_api.modules.connections.service import (
    ConnectionStateError,
    ScanTarget,
    active_connection_ids,
    create_connection,
    disconnect_connection,
    ended_connection_ids,
    get_connection,
    list_connections,
    scan_target,
)
from atesta_api.modules.connections.verification import (
    TenantMismatchError,
    VerificationReport,
    record_verification,
)

__all__ = [
    "ConnectionStateError",
    "ScanTarget",
    "TenantMismatchError",
    "VerificationReport",
    "active_connection_ids",
    "ended_connection_ids",
    "create_connection",
    "disconnect_connection",
    "get_connection",
    "list_connections",
    "record_verification",
    "router",
    "scan_target",
]
