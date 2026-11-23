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
        json={"name": "GitHub Actions", "expires_in_days": days, "scopes": ["evidence:write"]},
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
    body = {"name": "CI", "expires_in_days": 30, "scopes": ["evidence:write"]}
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


def test_a_retired_control_is_refused_like_an_unknown_one(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])["token"]
    with superuser.begin() as conn:
        conn.execute(text("UPDATE controls SET retired_at = now() WHERE key = :k"), {"k": control})
    response = client.post(INGEST, json=_body(control), headers=_bearer(token))
    assert (response.status_code, response.json()["detail"]["code"]) == (
        422,
        "evidence.control_not_found",
    )


@pytest.mark.parametrize(
    ("field", "longest"),
    [
        ("title", "t" * 200),
        ("statement", "s" * 4000),
        ("source", "s" * 50),
        ("reference_url", "https://example.com/" + "p" * 1980),
        ("external_id", "e" * 200),
    ],
)
def test_each_field_takes_its_longest_value_and_refuses_one_more(
    client: TestClient, superuser: Engine, control: str, field: str, longest: str
) -> None:
    org, subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])["token"]
    assert len(longest) in (50, 200, 2000, 4000)
    fits = client.post(INGEST, json=_body(control, **{field: longest}), headers=_bearer(token))
    assert fits.status_code == 201, fits.text
    over = client.post(
        INGEST, json=_body(control, **{field: longest + "x"}), headers=_bearer(token)
    )
    assert over.status_code == 422


def test_a_token_name_has_one_to_one_hundred_characters(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    url = f"/api/v1/orgs/{org}/api-tokens"
    for name, status in (("n" * 100, 201), ("n" * 101, 422), ("", 422)):
        response = client.post(
            url,
            json={"name": name, "expires_in_days": 30, "scopes": ["evidence:write"]},
            headers=auth(subs["owner"]),
        )
        assert response.status_code == status, name


@pytest.mark.parametrize("path", ["/api/v1/me", "/api/v1/orgs/{org}/overview"])
def test_an_api_token_reads_nothing(client: TestClient, superuser: Engine, path: str) -> None:
    """One scope only, evidence:write: the token is not a session on any other route."""
    org, subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])["token"]
    response = client.get(path.format(org=org), headers=_bearer(token))
    assert response.status_code == 401


CREDENTIAL_LINKS = [
    "https://acct.blob.core.windows.net/c/doc.pdf?sv=2024-01-01&sig=abc",
    "https://b.s3.eu-south-2.amazonaws.com/d.pdf?X-Amz-Signature=y",
    "https://storage.googleapis.com/b/d.pdf?X-Goog-Signature=y",
    "https://example.test/doc?TOKEN=abc",
    "https://example.test/doc#access_token=abc",
]


@pytest.mark.parametrize("link", CREDENTIAL_LINKS)
def test_a_link_that_is_itself_a_credential_is_never_stored(
    client: TestClient, superuser: Engine, control: str, link: str
) -> None:
    """Statements are append-only: a stored credential could never be purged (rule 2, #256)."""
    org, subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])["token"]
    result = client.post(INGEST, json=_body(control, reference_url=link), headers=_bearer(token))
    assert (result.status_code, result.json()["detail"]["code"]) == (422, "request.invalid")
    with superuser.connect() as conn:
        stored = text("SELECT count(*) FROM evidence WHERE organization_id = :o")
        assert conn.execute(stored, {"o": org}).scalar_one() == 0


def test_a_link_with_a_harmless_query_is_kept(
    client: TestClient, superuser: Engine, control: str
) -> None:
    org, subs = org_with(client, superuser)
    token = _token(client, org, subs["owner"])["token"]
    link = "https://contoso.sharepoint.com/sites/sec/Restore.docx?web=1"
    result = client.post(INGEST, json=_body(control, reference_url=link), headers=_bearer(token))
    assert result.status_code == 201, result.text


def test_record_attestation_refuses_a_credential_link_from_any_caller(
    db_rollback: Session, control: str
) -> None:
    """The last barrier: routines, training and ingestion all write through it."""
    from atesta_api.modules.evidence.api import CredentialLinkError, record_attestation
    from atesta_api.modules.identity.api import ContextReason, enter_org_context

    from .conftest import ORG_A

    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    with pytest.raises(CredentialLinkError):
        record_attestation(
            db_rollback,
            organization_id=ORG_A,
            author=uuid.uuid4(),
            control_key=control,
            title="t",
            statement="s",
            reference_url=CREDENTIAL_LINKS[0],
        )
