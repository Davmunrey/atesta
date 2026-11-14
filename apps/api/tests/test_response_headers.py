"""API responses are never cached or MIME-sniffed, whatever sits in front (web-shell spec)."""

import pytest
from atesta_api.main import app
from atesta_api.platform.errors import install_error_handlers
from atesta_api.platform.headers import install_response_headers
from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

EXPECTED = {"cache-control": "no-store", "x-content-type-options": "nosniff"}


def _app() -> FastAPI:
    test_app = FastAPI()
    install_error_handlers(test_app)
    install_response_headers(test_app)

    @test_app.get("/ok")
    def ok() -> dict[str, str]:
        return {"email": "ana@example.com"}

    @test_app.get("/denied")
    def denied() -> None:
        raise HTTPException(status_code=401, detail={"code": "auth.invalid_token"})

    @test_app.get("/redirect")
    def redirect() -> RedirectResponse:
        return RedirectResponse("/app", status_code=302)

    @test_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected")

    return test_app


@pytest.mark.parametrize(
    ("path", "status"),
    [("/ok", 200), ("/denied", 401), ("/redirect", 302), ("/missing", 404), ("/boom", 500)],
)
def test_every_response_carries_the_headers(path: str, status: int) -> None:
    client = TestClient(_app(), raise_server_exceptions=False, follow_redirects=False)
    response = client.get(path)
    assert response.status_code == status
    assert {name: response.headers.get(name) for name in EXPECTED} == EXPECTED


def test_the_real_app_installs_them() -> None:
    response = TestClient(app).get("/health")
    assert {name: response.headers.get(name) for name in EXPECTED} == EXPECTED
