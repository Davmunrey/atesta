"""Control workspaces use real PostgreSQL, tenant roles and immutable submissions."""

import json
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import WEB_ORIGIN, auth, new_sub
from .test_bff import signed_in
from .test_members import events, org_with


@pytest.fixture
def workspace(superuser: Engine) -> Iterator[str]:
    key = f"workspace_{uuid.uuid4().hex}"
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO controls (key, title_es, title_en, description_es,"
                " description_en, manual)"
                " VALUES (:k, 'Control sintético', 'Synthetic control', 'Guía', 'Guide', true)"
            ),
            {"k": key},
        )
        conn.execute(
            text(
                "INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes,"
                " status, attributes) VALUES (:k, 'Synthetic', '1', 'EU', 'test', 'test',"
                " 'released',"
                " CAST(:a AS jsonb))"
            ),
            {"k": key, "a": json.dumps({"preparation_controls": [key]})},
        )
    yield key
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM frameworks WHERE key = :k"), {"k": key})
        conn.execute(text("DELETE FROM controls WHERE key = :k"), {"k": key})


def statement(**changes: Any) -> dict[str, Any]:
    return {
        "submission_id": str(uuid.uuid4()),
        "title": "Synthetic policy",
        "statement": "Synthetic policy approved for this test.",
        "reference_url": "https://example.test/policy",
        **changes,
    }


def test_statement_retry_pagination_and_audit(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    base = f"/api/v1/orgs/{org}/controls/{workspace}"
    headers = auth(subs["mem"])
    empty = client.get(base + "/evidence", headers=headers)
    assert empty.status_code == 200
    assert empty.json() == {"total": 0, "items": []}
    payload = statement(title="  Synthetic policy  ")
    first = client.post(base + "/evidence", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert first.json()["title"] == "Synthetic policy"
    assert client.post(base + "/evidence", headers=headers, json=payload).json() == first.json()
    assert (
        client.post(
            base + "/evidence", headers=headers, json={**payload, "statement": "Changed"}
        ).status_code
        == 409
    )
    second = client.post(base + "/evidence", headers=headers, json=statement())
    assert second.status_code == 201
    page = client.get(base + "/evidence?limit=1", headers=headers).json()
    assert page["total"] == 2 and len(page["items"]) == 1
    next_page = client.get(base + "/evidence?limit=1&offset=1", headers=headers).json()
    assert page["items"][0]["id"] != next_page["items"][0]["id"]
    assert "storage_key" not in json.dumps(page)
    assert events(superuser, org, "evidence.statement_recorded") == 2
    with superuser.connect() as conn:
        metadata = (
            conn.execute(
                text(
                    "SELECT metadata FROM audit_events WHERE organization_id = :o"
                    " AND action = 'evidence.statement_recorded'"
                ),
                {"o": org},
            )
            .scalars()
            .all()
        )
    assert "Synthetic" not in json.dumps(metadata)
    assert "example.test" not in json.dumps(metadata)


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"title": "null\x00title"},
        {"statement": " "},
        {"statement": "x" * 10001},
        {"reference_url": "http://example.test"},
        {"reference_url": "https://u:p@example.test"},
        {"reference_url": "javascript:alert(1)"},
        {"reference_url": "https://example.test/\npath"},
        {"unknown": "field"},
    ],
)
def test_invalid_statement_is_rejected(
    client: TestClient, superuser: Engine, workspace: str, changes: dict[str, Any]
) -> None:
    org, subs = org_with(client, superuser)
    result = client.post(
        f"/api/v1/orgs/{org}/controls/{workspace}/evidence",
        headers=auth(subs["owner"]),
        json=statement(**changes),
    )
    assert result.status_code == 422
    assert events(superuser, org, "evidence.statement_recorded") == 0


def test_workspace_hides_foreign_and_invisible_controls(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser)
    base = f"/api/v1/orgs/{org}/controls/{workspace}"
    assert client.get(base + "/evidence", headers=auth(new_sub())).status_code == 404
    headers = auth(subs["owner"])
    with superuser.begin() as conn:
        conn.execute(
            text("UPDATE frameworks SET status = 'draft' WHERE key = :k"), {"k": workspace}
        )
    assert client.get(base + "/evidence", headers=headers).status_code == 404
    assert client.post(base + "/evidence", headers=headers, json=statement()).status_code == 404


def test_concurrent_retries_create_one_record_and_one_event(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser)
    url = f"/api/v1/orgs/{org}/controls/{workspace}/evidence"
    payload = statement()

    def submit(_: int) -> dict[str, Any]:
        result = client.post(url, headers=auth(subs["owner"]), json=payload)
        assert result.status_code == 201
        return dict(result.json())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    assert events(superuser, org, "evidence.statement_recorded") == 1


def test_tenant_isolation_and_author_conflict(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser, mem="member")
    other, theirs = org_with(client, superuser)
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence"
    other_path = f"/api/v1/orgs/{other}/controls/{workspace}/evidence"
    payload = statement()
    first = client.post(path, headers=auth(subs["owner"]), json=payload)
    assert first.status_code == 201
    assert client.post(path, headers=auth(subs["mem"]), json=payload).status_code == 409
    assert client.get(other_path, headers=auth(theirs["owner"])).json()["total"] == 0
    second = client.post(other_path, headers=auth(theirs["owner"]), json=payload)
    assert second.status_code == 201 and second.json()["id"] != first.json()["id"]
    with superuser.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM score_snapshots WHERE organization_id = :o"), {"o": org}
            ).scalar_one()
            == 0
        )


def test_cookie_submission_requires_same_origin(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser)
    signed_in(client, subs["owner"])
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence"
    assert client.post(path, json=statement()).status_code == 403
    assert (
        client.post(
            path, json=statement(), headers={"Origin": "https://elsewhere.example"}
        ).status_code
        == 403
    )
    assert client.post(path, json=statement(), headers={"Origin": WEB_ORIGIN}).status_code == 201


def test_statements_are_append_only(db_rollback: Session) -> None:
    from .conftest import ORG_A

    enter_org_context(db_rollback, ORG_A, ContextReason.MEMBERSHIP)
    for sql in (
        "UPDATE evidence_statements SET statement = 'changed'",
        "DELETE FROM evidence_statements",
    ):
        with pytest.raises(DBAPIError, match="permission denied"), db_rollback.begin_nested():
            db_rollback.execute(text(sql))


def test_mapping_visibility_and_retirement(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser)
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence"
    headers = auth(subs["owner"])
    with superuser.begin() as conn:
        conn.execute(
            text("UPDATE frameworks SET attributes = '{}' WHERE key = :k"), {"k": workspace}
        )
        conn.execute(
            text(
                "INSERT INTO requirements (framework_key, code, title_es, source)"
                " VALUES (:k, 'R1', 'Test', 'test')"
            ),
            {"k": workspace},
        )
        conn.execute(
            text(
                "INSERT INTO mappings (framework_key, requirement_code, control_key,"
                " rationale, source) VALUES (:k, 'R1', :k, 'test', 'test')"
            ),
            {"k": workspace},
        )
    try:
        assert client.get(path, headers=headers).status_code == 200
        with superuser.begin() as conn:
            conn.execute(
                text("UPDATE controls SET retired_at = now() WHERE key = :k"), {"k": workspace}
            )
        assert client.post(path, headers=headers, json=statement()).status_code == 404
    finally:
        with superuser.begin() as conn:
            conn.execute(text("DELETE FROM mappings WHERE framework_key = :k"), {"k": workspace})
            conn.execute(
                text("DELETE FROM requirements WHERE framework_key = :k"), {"k": workspace}
            )


def test_audit_failure_rolls_back_evidence(
    client: TestClient, superuser: Engine, workspace: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from atesta_api.modules.evidence import routes

    org, subs = org_with(client, superuser)
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence"

    def fail_audit(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr(routes, "record", fail_audit)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post(path, headers=auth(subs["owner"]), json=statement())
    assert client.get(path, headers=auth(subs["owner"])).json()["total"] == 0


def test_scan_evidence_is_readable_without_storage_keys(
    client: TestClient, superuser: Engine, workspace: str
) -> None:
    org, subs = org_with(client, superuser)
    evidence_id = uuid.uuid4()
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO evidence (id, organization_id, kind, title, storage_key, sha256,"
                " media_type, size_bytes, source_type, source_id, collected_at)"
                " VALUES (:e, :o, 'scan_output', 'Synthetic scan', :key, :hash,"
                " 'application/json', 10, 'scan', :scan, now())"
            ),
            {
                "e": evidence_id,
                "o": org,
                "key": f"{org}/scan.json",
                "hash": "a" * 64,
                "scan": uuid.uuid4(),
            },
        )
        conn.execute(
            text("INSERT INTO evidence_controls VALUES (:e, :k, :o)"),
            {"e": evidence_id, "o": org, "k": workspace},
        )
    path = f"/api/v1/orgs/{org}/controls/{workspace}/evidence"
    headers = auth(subs["owner"])
    page = client.get(path, headers=headers).json()
    assert page["items"][0]["statement"] is None and page["total"] == 1
    assert "storage_key" not in json.dumps(page)
    for query in ("?limit=51", "?offset=-1", "?limit=0"):
        assert client.get(path + query, headers=headers).status_code == 422
