"""Every error body carries a stable code and no prose or echoed input (identity-auth spec)."""

from typing import Any

from atesta_api.main import app
from atesta_api.platform.errors import install_error_handlers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import DataError


class Body(BaseModel):
    email: str
    count: int


def _app() -> FastAPI:
    test_app = FastAPI()
    install_error_handlers(test_app)

    @test_app.post("/items/{item_id}")
    def create(item_id: int, body: Body) -> dict[str, Any]:
        return {}

    @test_app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret detail with a token tok-abc")

    return test_app


def test_validation_error_is_a_code_with_field_names_only() -> None:
    client = TestClient(_app())
    response = client.post("/items/x", json={"email": "secret@example.com", "count": "many"})
    assert response.status_code == 422
    assert response.json() == {
        "detail": {"code": "request.invalid", "fields": ["body.count", "path.item_id"]}
    }
    assert "secret@example.com" not in response.text


def test_missing_and_malformed_bodies_are_request_invalid() -> None:
    client = TestClient(_app())
    for kwargs in (
        {},
        {"content": b"{not json", "headers": {"Content-Type": "application/json"}},
    ):
        response = client.post("/items/1", **kwargs)  # type: ignore[arg-type]
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "request.invalid"


def test_unhandled_error_is_server_error_without_details() -> None:
    response = TestClient(_app(), raise_server_exceptions=False).get("/boom")
    assert (response.status_code, response.json()) == (500, {"detail": {"code": "server.error"}})
    assert "tok-abc" not in response.text


def test_unknown_route_and_method_have_codes() -> None:
    client = TestClient(_app())
    assert client.get("/nope").json() == {"detail": {"code": "request.not_found"}}
    wrong = client.delete("/boom")
    assert (wrong.status_code, wrong.json()) == (
        405,
        {"detail": {"code": "request.method_not_allowed"}},
    )


def test_the_api_installs_the_handlers() -> None:
    assert TestClient(app).get("/api/v1/nope").json() == {"detail": {"code": "request.not_found"}}


def _data_error_app(message: str) -> FastAPI:
    test_app = FastAPI()
    install_error_handlers(test_app)

    @test_app.get("/store")
    def store() -> None:
        raise DataError("INSERT ...", {}, Exception(message))

    return test_app


def test_text_postgresql_cannot_store_is_invalid_input() -> None:
    response = TestClient(_data_error_app("PostgreSQL text fields cannot contain NUL (0x00) bytes"))
    reply = response.get("/store")
    assert reply.status_code == 422
    assert reply.json() == {"detail": {"code": "request.invalid", "fields": []}}


def test_any_other_data_error_is_still_a_logged_server_error() -> None:
    client = TestClient(_data_error_app("numeric field overflow"), raise_server_exceptions=False)
    reply = client.get("/store")
    assert (reply.status_code, reply.json()) == (500, {"detail": {"code": "server.error"}})
    assert "overflow" not in reply.text
