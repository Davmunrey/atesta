"""A minimal Google Admin SDK reader for the verifier (scanner-connectors spec, Google verifier).

GET only, under `https://admin.googleapis.com/` only. Pages follow `nextPageToken` as a query
parameter, never a URL taken from an answer, so the token is never sent anywhere else. Errors
carry status codes, never response bodies (rule 2: Google's messages can name users).
"""

from collections.abc import Mapping
from typing import Any

import httpx

ADMIN_ROOT = "https://admin.googleapis.com/"
MAX_PAGES = 100
_DENIED = frozenset({400, 401, 403, 404})


class GoogleTransientError(Exception):
    """429, 5xx, a network failure or a malformed answer: retried with the scan."""


class GoogleDeniedError(Exception):
    """400, 401, 403 or 404: the token may not read this, or the object does not exist."""

    def __init__(self, message: str, status: int = 403) -> None:
        super().__init__(message)
        self.status = status


class GoogleApi:
    def __init__(self, token: str, client: httpx.Client) -> None:
        self._headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        self._client = client

    def _fetch(self, path: str, params: Mapping[str, str] | None) -> Any:
        if not path.startswith("admin/") or "://" in path:
            raise ValueError("the verifier reads relative Admin SDK paths only")
        try:
            response = self._client.get(ADMIN_ROOT + path, params=params, headers=self._headers)
        except httpx.HTTPError:
            raise GoogleTransientError("google unreachable") from None
        status = response.status_code
        if status in _DENIED:
            raise GoogleDeniedError(f"google answered {status}", status)
        if status != 200:
            raise GoogleTransientError(f"google answered {status}")
        try:
            return response.json()
        except ValueError:
            raise GoogleTransientError("google answered with something that is not JSON") from None

    def get(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        return self._fetch(path, params)

    def get_all(
        self, path: str, items_key: str, params: Mapping[str, str] | None = None
    ) -> list[Any]:
        query = dict(params or {})
        items: list[Any] = []
        for _ in range(MAX_PAGES):
            page = self._fetch(path, query)
            if not isinstance(page, dict):
                raise GoogleTransientError("a page is not an object")
            found = page.get(items_key, [])  # Google omits an empty list
            next_token = page.get("nextPageToken")
            if not isinstance(found, list) or not isinstance(next_token, str | None):
                raise GoogleTransientError("a page is malformed")
            items.extend(found)
            if not next_token:
                return items
            query["pageToken"] = next_token
        raise GoogleTransientError("too many pages")
