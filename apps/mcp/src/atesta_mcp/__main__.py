"""Local stdio MCP server (mcp-server spec): `atesta-mcp` or `python -m atesta_mcp`.

Reads ATESTA_API_URL and ATESTA_API_KEY from the environment, as the MCP specification asks
stdio servers to do, and calls the Atesta API over HTTPS with that key. It never prints the key.
"""

import os
import sys
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any
from urllib.parse import urlsplit

import httpx
from mcp.server.mcpserver import Context

from atesta_mcp.server import build_server

LOCAL_HOSTS = {"localhost", "127.0.0.1"}


class ConfigError(Exception):
    pass


def settings(env: Mapping[str, str]) -> tuple[str, str, str]:
    """The API's base URL, the key and the language; refuses anything unsafe or missing."""
    url = env.get("ATESTA_API_URL", "").rstrip("/")
    key = env.get("ATESTA_API_KEY", "")
    language = env.get("ATESTA_LANGUAGE", "es")
    parts = urlsplit(url)
    local = parts.scheme == "http" and parts.hostname in LOCAL_HOSTS
    if not url or not (parts.scheme == "https" or local) or not parts.hostname:
        raise ConfigError("ATESTA_API_URL must be an https:// address (http only for localhost)")
    if not key.startswith("atesta_"):
        raise ConfigError("ATESTA_API_KEY must hold an Atesta API key (it starts with atesta_)")
    if language not in ("es", "en"):
        raise ConfigError("ATESTA_LANGUAGE must be es or en")
    return url, key, language


def main() -> None:
    try:
        url, key, language = settings(os.environ)
    except ConfigError as problem:
        print(f"atesta-mcp: {problem}", file=sys.stderr)
        raise SystemExit(2) from None
    headers = {"Authorization": f"Bearer {key}", "Accept-Language": language}

    def connect(ctx: Context[Any, Any]) -> AbstractAsyncContextManager[httpx.AsyncClient]:
        return httpx.AsyncClient(base_url=url, headers=headers, timeout=30.0)

    build_server(connect).run("stdio")


if __name__ == "__main__":
    main()
