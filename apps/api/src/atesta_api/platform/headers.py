"""Headers the API sets on its own responses (web-shell spec, Security headers).

Responses carry per-user data under URLs shared by every user (`/api/v1/me`), and the web CSP
trusts everything on the origin. So the API itself forbids caching and MIME sniffing, and does
not rely on a CDN behaviour being configured for it.
"""

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

RESPONSE_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class ResponseHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in RESPONSE_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self._app(scope, receive, send_with_headers)


def install_response_headers(app: FastAPI) -> None:
    app.add_middleware(ResponseHeadersMiddleware)
