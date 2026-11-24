"""API keys v2 (api-keys-v2 spec): scopes, rate limits and the usage log, on real PostgreSQL."""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_members import org_with
from .test_rbac import _add, _future

INGEST = "/api/v1/ingest/evidence"
KEY = "/api/v1/key"
READ = ["compliance:read", "incidents:read"]
WRITE = ["evidence:write", "assessment:propose", "routines:write"]


def make_key(
    client: TestClient,
    org: str,
    sub: str,
    scopes: list[str],
    limit: int | None = None,
) -> dict:  # type: ignore[type-arg]  # JSON body
    body: dict[str, object] = {"name": "Agent", "expires_in_days": 30, "scopes": scopes}
    if limit is not None:
        body["rate_limit_per_minute"] = limit
    response = client.post(f"/api/v1/orgs/{org}/api-tokens", json=body, headers=auth(sub))
    assert response.status_code == 201, response.text
    return response.json()


def bearer(token: str, language: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if language:
        headers["Accept-Language"] = language
    return headers


@pytest.fixture
def control(superuser: Engine) -> Iterator[str]:
    key = f"ctl.keys_{uuid.uuid4().hex[:12]}"
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO controls (key, title_es, title_en, description_es,"
                " description_en, manual) VALUES (:k, 'C', 'C', 'D', 'D', true)"
            ),
            {"k": key},
        )
    yield key
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM evidence_controls WHERE control_key = :k"), {"k": key})
        conn.execute(text("DELETE FROM controls WHERE key = :k"), {"k": key})


def evidence_body(control: str) -> dict[str, str]:
    return {"control": control, "title": "T", "statement": "S", "source": "agent"}


def test_a_key_carries_the_scopes_and_limit_its_admin_chose(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    created = make_key(client, org, subs["owner"], READ, limit=5)
    assert (created["scopes"], created["rate_limit_per_minute"], created["read_only"]) == (
        READ,
        5,
        True,
    )
    writer = make_key(client, org, subs["owner"], ["incidents:read", "evidence:write"])
    assert (writer["rate_limit_per_minute"], writer["read_only"]) == (60, False)
    listed = client.get(f"/api/v1/orgs/{org}/api-tokens", headers=auth(subs["owner"])).json()
    assert {tuple(k["scopes"]) for k in listed} == {
        tuple(READ),
        ("incidents:read", "evidence:write"),
    }
    me = client.get(KEY, headers=bearer(created["token"]))
    assert me.status_code == 200, me.text
    assert me.json() == {
        "name": "Agent",
        "prefix": created["prefix"],
        "scopes": READ,
        "rate_limit_per_minute": 5,
        "expires_at": created["expires_at"],
    }


@pytest.mark.parametrize(
    "wrong",
    [
        {"scopes": []},
        {"scopes": ["evidence:write", "evidence:write"]},
        {"scopes": ["admin:all"]},
        {"scopes": None},
        {"rate_limit_per_minute": 0},
        {"rate_limit_per_minute": 601},
    ],
)
def test_scopes_and_limits_are_checked(
    client: TestClient, superuser: Engine, wrong: dict[str, object]
) -> None:
    org, subs = org_with(client, superuser)
    body = {"name": "CI", "expires_in_days": 30, "scopes": ["evidence:write"], **wrong}
    response = client.post(f"/api/v1/orgs/{org}/api-tokens", json=body, headers=auth(subs["owner"]))
    assert response.status_code == 422, wrong


def test_a_key_without_scopes_in_the_request_is_refused(
    client: TestClient, superuser: Engine
) -> None:
    """Least privilege by default: there is no default scope."""
    org, subs = org_with(client, superuser)
    body = {"name": "CI", "expires_in_days": 30}
    response = client.post(f"/api/v1/orgs/{org}/api-tokens", json=body, headers=auth(subs["owner"]))
    assert response.status_code == 422


def test_a_read_only_key_cannot_write_evidence(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser)
    reader = make_key(client, org, subs["owner"], READ)
    refused = client.post(INGEST, json=evidence_body(control), headers=bearer(reader["token"]))
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "identity.api_token_scope"
    assert refused.json()["detail"]["scope"] == "evidence:write"
    assert refused.json()["detail"]["message"]
    writer = make_key(client, org, subs["owner"], ["evidence:write"])
    accepted = client.post(INGEST, json=evidence_body(control), headers=bearer(writer["token"]))
    assert accepted.status_code == 201, accepted.text


def test_the_limit_counts_accepted_requests_in_the_last_minute(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["compliance:read"], limit=2)
    token = key["token"]
    # Refused for scope: not counted.
    assert (
        client.post(INGEST, json=evidence_body(control), headers=bearer(token)).status_code == 403
    )
    assert client.get(KEY, headers=bearer(token)).status_code == 200
    assert client.get(KEY, headers=bearer(token)).status_code == 200
    spanish = client.get(KEY, headers=bearer(token))
    english = client.get(KEY, headers=bearer(token, "en-GB,en;q=0.9"))
    for response in (spanish, english):
        assert response.status_code == 429
        assert response.json()["detail"]["code"] == "identity.api_token_rate_limited"
        assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert spanish.json()["detail"]["message"] != english.json()["detail"]["message"]
    with superuser.begin() as conn:
        counted = conn.scalar(
            text("SELECT count(*) FROM api_token_usage WHERE token_id = :t"), {"t": key["id"]}
        )
        # An older window does not count: the next request is accepted again.
        conn.execute(
            text("UPDATE api_token_usage SET at = at - interval '61 seconds' WHERE token_id = :t"),
            {"t": key["id"]},
        )
    assert counted == 2
    assert client.get(KEY, headers=bearer(token)).status_code == 200


def test_the_usage_log_holds_routes_and_scopes_never_content(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    key = make_key(client, org, subs["owner"], ["evidence:write"])
    secret_title = "Texto del cliente que no debe aparecer"
    body = {**evidence_body(control), "title": secret_title, "external_id": "run-7"}
    assert client.post(INGEST, json=body, headers=bearer(key["token"])).status_code == 201
    assert client.get(KEY, headers=bearer(key["token"])).status_code == 200
    url = f"/api/v1/orgs/{org}/api-tokens/{key['id']}/usage"
    usage = client.get(url, headers=auth(subs["owner"]))
    assert usage.status_code == 200, usage.text
    data = usage.json()
    assert data["last_24h"] == 2
    assert [(r["method"], r["route"], r["scope"]) for r in data["recent"]] == [
        ("GET", "/api/v1/key", None),
        ("POST", "/api/v1/ingest/evidence", "evidence:write"),
    ]
    with superuser.begin() as conn:
        stored = conn.execute(
            text("SELECT row_to_json(u)::text FROM api_token_usage u WHERE token_id = :t"),
            {"t": key["id"]},
        ).scalars()
        dump = " ".join(stored)
    assert secret_title not in dump and "run-7" not in dump and control not in dump
    assert client.get(url, headers=auth(subs["ana"])).status_code == 403
    auditor = _add(superuser, client, org, "auditor", _future())
    assert client.get(url, headers=auth(auditor)).status_code == 403
    other, other_subs = org_with(client, superuser)
    wrong = f"/api/v1/orgs/{other}/api-tokens/{key['id']}/usage"
    assert client.get(wrong, headers=auth(other_subs["owner"])).status_code == 404


def test_existing_keys_keep_exactly_evidence_write() -> None:
    """Migration 0025 on a database holding a key from before it: the key keeps its one scope."""
    import os

    from alembic import command
    from alembic.config import Config
    from atesta_api.platform.db import make_engine
    from sqlalchemy.engine import make_url

    from .conftest import API_DIR

    admin_url = os.environ.get("ATESTA_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("ATESTA_TEST_DATABASE_URL not set")
    admin = make_url(admin_url)
    name = f"atesta_keys_{uuid.uuid4().hex[:8]}"
    server = make_engine(admin, sslmode="disable", null_pool=True)
    with server.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    url = admin.set(database=name)
    engine = make_engine(url, sslmode="disable", null_pool=True)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql((API_DIR / "migrations" / "bootstrap.sql").read_text())
        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("sqlalchemy.url", url.render_as_string(hide_password=False))
        config.attributes["role"] = "atesta_owner"
        command.upgrade(config, "0024")
        org, user = uuid.uuid4(), uuid.uuid4()
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:o, 'Old')"), {"o": org}
            )
            conn.execute(
                text(
                    "INSERT INTO users (id, cognito_sub, email, email_verified)"
                    " VALUES (:u, 'old', 'o@x.test', true)"
                ),
                {"u": user},
            )
            conn.execute(
                text(
                    "INSERT INTO api_tokens (organization_id, id, name, prefix, token_sha256,"
                    " created_by, expires_at) VALUES (:o, gen_random_uuid(), 'Old', 'atesta_abcde',"
                    " repeat('a', 64), :u, now() + interval '30 days')"
                ),
                {"o": org, "u": user},
            )
        command.upgrade(config, "head")
        with engine.begin() as conn:
            row = conn.execute(text("SELECT scopes, rate_limit_per_minute FROM api_tokens")).one()
        assert (row.scopes, row.rate_limit_per_minute) == (["evidence:write"], 60)
    finally:
        engine.dispose()
        with server.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("api_tokens", {"SELECT", "INSERT", "UPDATE"}),
        ("api_token_usage", {"SELECT", "INSERT", "DELETE"}),
    ],  # DELETE: retention, issue 353
)
def test_usage_grants(superuser: Engine, table: str, expected: set[str]) -> None:
    with superuser.begin() as conn:
        grants = set(
            conn.scalars(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants"
                    " WHERE grantee = 'atesta_app' AND table_name = :t"
                ),
                {"t": table},
            )
        )
    assert grants == expected
