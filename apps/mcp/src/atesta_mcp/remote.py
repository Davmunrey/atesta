"""Hosted remote MCP server (mcp-server spec): Streamable HTTP, mounted by the API at /mcp only
with ATESTA_MCP_REMOTE=1 (ADR-016).

Stateless and JSON-only. A request without a credential gets 401 before any MCP handling. Two
credentials open it:

- an Atesta API key. Tools forward that header, and Accept-Language, to the same API
  in-process, where the key is checked like any other call;
- an OAuth access token issued for this server (mcp-oauth spec, ADR-016 amendment 1), when the
  host turns OAuth on. The token is verified here and never forwarded: the API is entered
  in-process as that agent, and the grant recorded in Atesta decides what it may do.

Either way scopes, the rate limit, the usage log, tenancy and audit happen in the API.
"""

import json
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

import anyio.to_thread
import httpx
from mcp.server.mcpserver import Context
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from atesta_mcp.server import build_server

BEARER = re.compile(r"^Bearer atesta_[A-Za-z0-9_-]{20,193}$")
OAUTH_BEARER = re.compile(r"^Bearer ([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)$")
INTERNAL = "http://atesta.internal"  # in-process only: never resolved or reached on a network
# Set by the gate after it has verified an OAuth token, and stripped from every incoming
# request first. It only tells this module which in-process app to call; the API never reads it.
AGENT_HEADER = b"x-atesta-agent"


class AgentAccess(Protocol):
    """What the host provides for OAuth (the API's identity module). All three may change at
    run time, so they are asked on each request."""

    def challenge(self) -> str | None:
        """The WWW-Authenticate value of a 401, or None while OAuth is off."""

    def verify(self, token: str) -> str | None:
        """An opaque reference for a token issued for this server, or None when it is refused."""

    def enter(self, api: ASGIApp, reference: str) -> ASGIApp:
        """The API, entered in-process as that verified agent."""


class BearerGate:
    """401 for any request without an Atesta key or, with OAuth on, a verified access token.
    The API checks the key itself; an OAuth token is verified here and goes no further."""

    def __init__(self, app: ASGIApp, agents: AgentAccess | None = None) -> None:
        self.app = app
        self.agents = agents

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = [(k, v) for k, v in scope.get("headers") or [] if k.lower() != AGENT_HEADER]
        authorization = dict(incoming).get(b"authorization", b"").decode("latin-1")
        if BEARER.match(authorization):
            await self.app({**scope, "headers": incoming}, receive, send)
            return
        challenge = self.agents.challenge() if self.agents else None
        token = OAUTH_BEARER.match(authorization)
        if self.agents is not None and challenge is not None and token:
            # Verifying may fetch the signing keys: never on the event loop.
            reference = await anyio.to_thread.run_sync(self.agents.verify, token.group(1))
            if reference is not None:
                kept = [(k, v) for k, v in incoming if k.lower() != b"authorization"]
                kept.append((AGENT_HEADER, reference.encode("ascii")))
                await self.app({**scope, "headers": kept}, receive, send)
                return
        body = json.dumps({"detail": {"code": "identity.api_token_invalid"}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", (challenge or "Bearer").encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def remote_app(
    api: ASGIApp,
    allowed_hosts: list[str],
    allowed_origins: list[str],
    agents: AgentAccess | None = None,
) -> tuple[ASGIApp, Callable[[], AbstractAsyncContextManager[None]]]:
    """The gated MCP app to mount, and the context manager the host's lifespan must enter."""

    def connect(ctx: Context[Any, Any]) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        incoming = ctx.headers or {}
        forwarded = {
            name: incoming[name]
            for name in ("authorization", "accept-language")
            if name in incoming
        }
        reference = incoming.get(AGENT_HEADER.decode())
        target = api
        if agents is not None and reference:  # set by the gate only, after verifying the token
            target = agents.enter(api, reference)
            forwarded.pop("authorization", None)
        transport = httpx.ASGITransport(app=target)
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
    return BearerGate(mcp_app, agents), server.session_manager.run
