"""Public interface of the connections module.

Planned: scan_target and record_verification (verifiers, PR 9). No API or worker process ever
reads a connector secret; connections hold references only.
"""

from atesta_api.modules.connections.routes import router
from atesta_api.modules.connections.service import (
    ConnectionStateError,
    active_connection_ids,
    create_connection,
    disconnect_connection,
    ended_connection_ids,
    get_connection,
    list_connections,
)

__all__ = [
    "ConnectionStateError",
    "active_connection_ids",
    "ended_connection_ids",
    "create_connection",
    "disconnect_connection",
    "get_connection",
    "list_connections",
    "router",
]
