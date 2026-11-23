"""Hosted remote MCP server (mcp-server spec): Streamable HTTP, mounted by the API at /mcp only
with ATESTA_MCP_REMOTE=1 (ADR-016).

Stateless and JSON-only. A request without an Atesta key in Authorization gets 401 before any MCP
handling. Tools forward that header, and Accept-Language, to the same API in-process, where the
key is checked like any other call: scopes, rate limit, usage log, tenancy and audit.
"""

import json
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from atesta_mcp.server import build_server

BEARER = re.compile(r"^Bearer atesta_[A-Za-z0-9_-]{20,193}$")
INTERNAL = "http://atesta.internal"  # in-process only: never resolved or reached on a network


class BearerGate:
    """401 for any request without a well-formed Atesta key; the API checks the key itself."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            if not BEARER.match(headers.get(b"authorization", b"").decode("latin-1")):
                body = json.dumps({"detail": {"code": "identity.api_token_invalid"}}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 401,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"www-authenticate", b"Bearer"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


def remote_app(
    api: ASGIApp, allowed_hosts: list[str], allowed_origins: list[str]
) -> tuple[ASGIApp, Callable[[], AbstractAsyncContextManager[None]]]:
    """The gated MCP app to mount, and the context manager the host's lifespan must enter."""

    def connect(ctx: Context[Any, Any]) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        incoming = ctx.headers or {}
        forwarded = {
            name: incoming[name]
            for name in ("authorization", "accept-language")
            if name in incoming
        }
        transport = httpx.ASGITransport(app=api)
        return httpx.AsyncClient(transport=transport, base_url=INTERNAL, headers=forwarded)

    server = build_server(connect)
    mcp_app = server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed_hosts,
            allowed_origins=allowed_origins,
        ),
    )
    return BearerGate(mcp_app), server.session_manager.run
