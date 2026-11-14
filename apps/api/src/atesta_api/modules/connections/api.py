"""Public interface of the connections module.

Planned: record_verification (verifiers, PR 9). No API or worker process ever
reads a connector secret; connections hold references only.
"""

from atesta_api.modules.connections.routes import router
from atesta_api.modules.connections.service import (
    ConnectionStateError,
    ScanTarget,
    active_connection_ids,
    create_connection,
    disconnect_connection,
    get_connection,
    list_connections,
    scan_target,
)

__all__ = [
    "ConnectionStateError",
    "ScanTarget",
    "active_connection_ids",
    "create_connection",
    "disconnect_connection",
    "get_connection",
    "list_connections",
    "router",
    "scan_target",
]
