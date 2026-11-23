"""Calls to the Atesta API on behalf of a tool. The key travels only in the Authorization header,
set by whoever built the httpx client; this module never sees or prints it (rule 2)."""

from typing import Any
from urllib.parse import quote

import httpx


class AtestaError(Exception):
    """An API refusal, carried to the agent as a tool error with its stable code."""

    def __init__(self, status: int, code: str, message: str, retry_after: str | None) -> None:
        super().__init__(code)
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after

    def describe(self) -> str:
        text = f"Atesta API refused the call (HTTP {self.status}, code {self.code})."
        if self.message:
            text += f" {self.message}"
        if self.retry_after:
            text += f" Retry after {self.retry_after} seconds; do not retry sooner."
        return text


def _detail(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    detail = body.get("detail") if isinstance(body, dict) else None
    return detail if isinstance(detail, dict) else {}


async def call(
    http: httpx.AsyncClient,
    method: str,
    template: str,
    path: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    """One API call. Path values are percent-encoded, so no value can change the route."""
    url = template.format(**{k: quote(v, safe="") for k, v in (path or {}).items()})
    response = await http.request(method, url, json=body)
    if response.status_code >= 400:
        detail = _detail(response)
        code = str(detail.get("code", "request.error"))
        message = str(detail.get("message", ""))
        if code == "request.invalid" and detail.get("fields"):
            message = f"Invalid fields: {', '.join(map(str, detail['fields']))}."
        raise AtestaError(response.status_code, code, message, response.headers.get("retry-after"))
    return response.json()
