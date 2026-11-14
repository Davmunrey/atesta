"""A minimal Microsoft Graph v1.0 reader for the verifier (scanner-connectors spec).

GET only. Pages follow `@odata.nextLink` only while it stays under the Graph root, so the token
is never sent anywhere else. Errors carry status codes, never response bodies (rule 2).
"""

from collections.abc import Mapping
from typing import Any

import httpx

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
MAX_PAGES = 100


class GraphTransientError(Exception):
    """429, 5xx, a network failure or an answer that is not JSON: retried with the scan."""


class GraphDeniedError(Exception):
    """401, 403 or 404: the token may not read this, or the object does not exist."""

    def __init__(self, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.status = status


class Graph:
    def __init__(self, token: str, client: httpx.Client) -> None:
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._client = client

    def _fetch(self, url: str, params: Mapping[str, str] | None) -> Any:
        try:
            response = self._client.get(url, params=params, headers=self._headers)
        except httpx.HTTPError:
            raise GraphTransientError("graph unreachable") from None
        status = response.status_code
        if status in (401, 403, 404):
            raise GraphDeniedError(f"graph answered {status}", status)
        if status != 200:
            raise GraphTransientError(f"graph answered {status}")
        try:
            return response.json()
        except ValueError:
            raise GraphTransientError("graph answered with something that is not JSON") from None

    def get(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        return self._fetch(GRAPH_ROOT + path, params)

    def get_all(self, path: str, params: Mapping[str, str] | None = None) -> list[Any]:
        items: list[Any] = []
        url: str | None = GRAPH_ROOT + path
        for _ in range(MAX_PAGES):
            if url is None:
                return items
            page = self._fetch(url, params)
            params = None  # the next link carries them
            items.extend(page["value"])
            url = page.get("@odata.nextLink")
            if url is not None and not url.startswith(GRAPH_ROOT + "/"):
                raise GraphTransientError("a next link leaves Graph")
        raise GraphTransientError("too many pages")
