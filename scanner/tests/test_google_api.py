"""The verifier's Admin SDK reader (scanner-connectors spec, Google verifier contract, Reader).

GET only, admin.googleapis.com only. Pages follow `nextPageToken` as a parameter, so no URL from
an answer ever receives the token. Errors carry status codes, never response bodies (rule 2).
"""

from typing import Any

import httpx
import pytest
from atesta_scanner.google_api import (
    ADMIN_ROOT,
    MAX_PAGES,
    GoogleApi,
    GoogleDeniedError,
    GoogleTransientError,
)

PATH = "admin/directory/v1/customer/my_customer/roleassignments"


def api(handler: Any) -> GoogleApi:
    return GoogleApi("tok", httpx.Client(transport=httpx.MockTransport(handler)))


def test_pages_follow_the_page_token_on_the_same_host_with_the_bearer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if "pageToken" not in request.url.params:
            return httpx.Response(200, json={"items": [{"n": 1}], "nextPageToken": "p2"})
        return httpx.Response(200, json={"items": [{"n": 2}]})

    assert api(handler).get_all(PATH, "items", {"maxResults": "200"}) == [{"n": 1}, {"n": 2}]
    assert [r.method for r in seen] == ["GET", "GET"]
    assert all(str(r.url).startswith(ADMIN_ROOT + PATH) for r in seen)
    assert seen[1].url.params["pageToken"] == "p2" and seen[1].url.params["maxResults"] == "200"
    assert seen[0].headers["Authorization"] == "Bearer tok"


def test_a_page_without_items_is_empty_and_endless_pages_are_transient() -> None:
    assert api(lambda r: httpx.Response(200, json={"kind": "x"})).get_all(PATH, "items") == []
    calls: list[int] = []

    def forever(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json={"items": [], "nextPageToken": "again"})

    with pytest.raises(GoogleTransientError):
        api(forever).get_all(PATH, "items")
    assert len(calls) == MAX_PAGES


@pytest.mark.parametrize(
    "page",
    [{"items": {"not": "a list"}}, {"items": [], "nextPageToken": 7}, ["a", "list"]],
)
def test_a_malformed_page_is_transient(page: object) -> None:
    with pytest.raises(GoogleTransientError):
        api(lambda r: httpx.Response(200, json=page)).get_all(PATH, "items")


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (400, GoogleDeniedError),
        (401, GoogleDeniedError),
        (403, GoogleDeniedError),
        (404, GoogleDeniedError),
        (429, GoogleTransientError),
        (500, GoogleTransientError),
        (503, GoogleTransientError),
    ],
)
def test_status_codes_map_to_denied_or_transient(status: int, error: type[Exception]) -> None:
    body = {"error": {"message": "admin@example.es is not allowed"}}
    with pytest.raises(error) as raised:
        api(lambda r: httpx.Response(status, json=body)).get("admin/directory/v1/users/x")
    assert "admin@example.es" not in str(raised.value)  # never Google's message
    if isinstance(raised.value, GoogleDeniedError):
        assert raised.value.status == status


def test_a_network_failure_or_an_answer_that_is_not_json_is_transient() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(GoogleTransientError):
        api(down).get(PATH)
    with pytest.raises(GoogleTransientError):
        api(lambda r: httpx.Response(200, text="<html>")).get(PATH)


@pytest.mark.parametrize("path", ["https://evil.example/x", "/admin/x", "//evil.example/x"])
def test_only_relative_admin_paths_are_read(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        api(lambda r: httpx.Response(200, json={})).get(path)
