"""Evidence ingestion API (evidence-ingestion-api spec), on real PostgreSQL with RLS."""

import uuid
from collections.abc import Iterator

import pytest
from atesta_api.modules.identity.api import token_hash
from atesta_api.modules.identity.context import enter_api_token_context
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from .conftest import auth
from .test_members import events, org_with
from .test_rbac import _add, _future

INGEST = "/api/v1/ingest/evidence"


@pytest.fixture
def control(superuser: Engine) -> Iterator[str]:
    key = f"ctl.ingest_{uuid.uuid4().hex[:12]}"
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO controls (key, title_es, title_en, description_es,"
                " description_en, manual)"
                " VALUES (:k, 'Copias', 'Backups', 'Guía', 'Guide', true)"
            ),
            {"k": key},
        )
    yield key
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM evidence_controls WHERE control_key = :k"), {"k": key})
        conn.execute(text("DELETE FROM controls WHERE key = :k"), {"k": key})


def _token(client: TestClient, org: str, sub: str, days: int = 90) -> dict:  # type: ignore[type-arg]  # JSON body
    response = client.post(
        f"/api/v1/orgs/{org}/api-tokens",
        json={"name": "GitHub Actions", "expires_in_days": days},
        headers=auth(sub),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _body(control: str, **over: object) -> dict[str, object]:
    return {
        "control": control,
        "title": "Restore test",
        "statement": "Nightly restore of the billing database succeeded in 14 minutes.",
        "source": "github-actions",
        "reference_url": "https://github.com/example/infra/actions/runs/1",
        **over,
    }


def test_a_token_records_evidence_once_per_external_id(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser)
    created = _token(client, org, subs["owner"])
    token = created["token"]
    assert token.startswith("atesta_") and created["prefix"] == token[:12]
    first = client.post(INGEST, json=_body(control, external_id="run-1"), headers=_bearer(token))
    assert first.status_code == 201, first.text
    again = client.post(INGEST, json=_body(control, external_id="run-1"), headers=_bearer(token))
    assert (again.status_code, again.json()) == (
        200,
        {"evidence_id": first.json()["evidence_id"], "duplicate": True},
    )
    assert client.post(INGEST, json=_body(control), headers=_bearer(token)).status_code == 201
    with superuser.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT e.source_type, e.source_id, e.created_by, c.control_key"
                " FROM evidence e JOIN evidence_controls c ON c.organization_id = e.organization_id"
                " AND c.evidence_id = e.id WHERE e.organization_id = :o ORDER BY e.collected_at"
            ),
            {"o": org},
        ).all()
        owner = conn.scalar(
            text("SELECT user_id FROM memberships WHERE organization_id = :o"), {"o": org}
        )
    assert len(rows) == 2
    assert {(r.source_type, str(r.source_id), r.created_by, r.control_key) for r in rows} == {
        ("api", created["id"], owner, control)
    }
    listed = client.get(f"/api/v1/orgs/{org}/api-tokens", headers=auth(subs["owner"])).json()
    assert listed[0]["last_used_at"] and "token" not in listed[0]
    assert events(superuser, org, "evidence.ingested") == 2
    assert events(superuser, org, "api_token.created") == 1


def test_every_bad_token_gets_the_same_401(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser)
    revoked = _token(client, org, subs["owner"])
    expired = _token(client, org, subs["owner"])
    url = f"/api/v1/orgs/{org}/api-tokens/{revoked['id']}"
    assert client.delete(url, headers=auth(subs["owner"])).status_code == 204
    assert client.delete(url, headers=auth(subs["owner"])).status_code == 404
    with superuser.begin() as conn:
        conn.execute(
            text(
                "UPDATE api_tokens SET created_at = now() - interval '2 days',"
                " expires_at = now() - interval '1 day' WHERE id = :i"
            ),
            {"i": expired["id"]},
        )
    for headers in (
        {},
        {"Authorization": "Basic abc"},
        _bearer("atesta_" + "x" * 43),
        _bearer(revoked["token"]),
        _bearer(expired["token"]),
        auth(subs["owner"]),  # a person's session token is not an API token
    ):
        response = client.post(INGEST, json=_body(control), headers=headers)
        assert (response.status_code, response.json()["detail"]["code"]) == (
            401,
            "identity.api_token_invalid",
        ), headers
    assert events(superuser, org, "api_token.revoked") == 1


def test_ingestion_input_is_checked(client: TestClient, superuser: Engine, control: str) -> None:
    org, subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])["token"]
    unknown = client.post(INGEST, json=_body("ctl.nope"), headers=_bearer(token))
    assert (unknown.status_code, unknown.json()["detail"]["code"]) == (
        422,
        "evidence.control_not_found",
    )
    for wrong in (
        {"reference_url": "http://example.com"},
        {"statement": "   "},
        {"statement": "x" * 4001},
        {"source": "<script>"},
    ):
        assert (
            client.post(INGEST, json=_body(control, **wrong), headers=_bearer(token)).status_code
            == 422
        )
    in_query = client.post(f"{INGEST}?token={token}", json=_body(control), headers=_bearer(token))
    assert in_query.status_code == 400


def test_only_admins_manage_tokens(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, ana="member")
    auditor = _add(superuser, client, org, "auditor", _future())
    url = f"/api/v1/orgs/{org}/api-tokens"
    body = {"name": "CI", "expires_in_days": 30}
    for who in (subs["ana"], auditor):
        assert client.post(url, json=body, headers=auth(who)).status_code == 403
        assert client.get(url, headers=auth(who)).status_code == 403
    for wrong in ({"expires_in_days": 0}, {"expires_in_days": 366}, {"name": "  "}):
        assert (
            client.post(url, json={**body, **wrong}, headers=auth(subs["owner"])).status_code == 422
        )
    other, other_subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])
    assert (
        client.delete(
            f"/api/v1/orgs/{other}/api-tokens/{token['id']}", headers=auth(other_subs["owner"])
        ).status_code
        == 404
    )


def test_a_token_reads_only_its_own_row(
    client: TestClient, superuser: Engine, app_engine: Engine
) -> None:
    org_a, subs_a = org_with(client, superuser)
    org_b, subs_b = org_with(client, superuser)
    token_a = _token(client, org_a, subs_a["owner"])["token"]
    _token(client, org_b, subs_b["owner"])
    with app_engine.connect() as conn, conn.begin():
        session = Session(bind=conn)
        enter_api_token_context(session, token_hash(token_a))
        seen = session.execute(text("SELECT organization_id FROM api_tokens")).scalars().all()
        assert [str(o) for o in seen] == [org_a]
        changed = session.execute(text("UPDATE api_tokens SET name = 'x'"))
        assert changed.rowcount == 0  # type: ignore[attr-defined]  # the token policy only reads
        assert session.execute(text("SELECT count(*) FROM evidence")).scalar() == 0
        conn.rollback()


@pytest.mark.parametrize(
    ("table", "expected"),
    [("api_tokens", {"SELECT", "INSERT", "UPDATE"}), ("api_ingestions", {"SELECT", "INSERT"})],
)
def test_ingestion_grants(superuser: Engine, table: str, expected: set[str]) -> None:
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
