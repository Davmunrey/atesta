"""Dashboard reads: real PostgreSQL, authenticated requests, synthetic records only."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth, new_sub
from .test_members import org_with


@pytest.fixture
def overview_catalog(superuser: Engine) -> Iterator[dict[str, str]]:
    keys = {
        state: f"overview_{state}_{uuid.uuid4().hex}"
        for state in ("active", "unassessed", "draft", "retired")
    }
    with superuser.begin() as conn:
        for state, key in keys.items():
            conn.execute(
                text(
                    "INSERT INTO frameworks (key, name, version, jurisdiction, source,"
                    " license_notes, status, retired_at, catalog_version)"
                    " VALUES (:key, :name, 'current', 'EU', 'synthetic', 'test',"
                    " :status, :retired, 'v2')"
                ),
                {
                    "key": key,
                    "name": f"Synthetic {state}",
                    "status": "draft" if state == "draft" else "released",
                    "retired": datetime.now(UTC) if state == "retired" else None,
                },
            )
    yield keys
    with superuser.begin() as conn:
        conn.execute(
            text("DELETE FROM score_snapshots WHERE framework_key = ANY(:keys)"),
            {"keys": list(keys.values())},
        )
        conn.execute(
            text("DELETE FROM frameworks WHERE key = ANY(:keys)"), {"keys": list(keys.values())}
        )


def add_snapshot(engine: Engine, org: str, key: str, **overrides: Any) -> str:
    snapshot_id = str(uuid.uuid4())
    params = {
        "id": snapshot_id,
        "org": org,
        "key": key,
        "scan": str(uuid.uuid4()),
        "score": 50,
        "passed": 1,
        "failed": 1,
        "manual": 1,
        "na": 1,
        "at": datetime(2026, 1, 1, tzinfo=UTC),
        "scope": None,
        "supersedes": None,
        **overrides,
    }
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO score_snapshots (id, organization_id, framework_key,"
                " framework_version, catalog_version, scan_id, scope_id, score, passed, failed,"
                " manual, not_applicable, requirement_results, computed_at, supersedes_id)"
                " VALUES (:id, :org, :key, 'recorded', 'v1', :scan, :scope, :score,"
                " :passed, :failed, :manual, :na, '{}', :at, :supersedes)"
            ),
            params,
        )
    return str(params["id"])


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_overview_is_readable_by_every_member_without_inventing_results(
    client: TestClient, superuser: Engine, overview_catalog: dict[str, str], role: str
) -> None:
    org, subs = org_with(client, superuser, admin="admin", member="member")
    response = client.get(f"/api/v1/orgs/{org}/overview", headers=auth(subs[role]))
    assert response.status_code == 200
    data = response.json()
    assert data["scans"] == []
    assert data["evidence_count"] == 0
    frameworks = {f["key"]: f for f in data["frameworks"]}
    assert overview_catalog["active"] in frameworks
    assert frameworks[overview_catalog["active"]]["snapshot"] is None
    assert not {overview_catalog["draft"], overview_catalog["retired"]} & frameworks.keys()


def test_overview_requires_membership_and_does_not_enumerate_orgs(
    client: TestClient, superuser: Engine
) -> None:
    org, _ = org_with(client, superuser)
    url = f"/api/v1/orgs/{org}/overview"
    assert client.get(url).status_code == 401
    outsider = auth(new_sub())
    for target in (org, str(uuid.uuid4())):
        response = client.get(f"/api/v1/orgs/{target}/overview", headers=outsider)
        assert response.status_code == 404
        assert response.json() == {"detail": {"code": "identity.not_found"}}


def test_latest_snapshot_preserves_recorded_versions_and_ignores_narrow_scopes(
    client: TestClient, superuser: Engine, overview_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    key = overview_catalog["active"]
    scan = str(uuid.uuid4())
    original = add_snapshot(superuser, org, key, scan=scan)
    correction = add_snapshot(
        superuser,
        org,
        key,
        scan=scan,
        supersedes=original,
        score=None,
        passed=0,
        failed=0,
        at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    add_snapshot(
        superuser, org, key, scope=str(uuid.uuid4()), score=100, at=datetime(2026, 3, 1, tzinfo=UTC)
    )
    add_snapshot(superuser, org, overview_catalog["draft"])
    add_snapshot(superuser, org, overview_catalog["retired"])
    data = client.get(f"/api/v1/orgs/{org}/overview", headers=auth(subs["owner"])).json()
    frameworks = {f["key"]: f for f in data["frameworks"]}
    snapshot = frameworks[key]["snapshot"]
    assert snapshot["id"] == correction
    assert snapshot["score"] is None
    assert (snapshot["passed"], snapshot["failed"], snapshot["manual"]) == (0, 0, 1)
    assert (snapshot["framework_version"], snapshot["catalog_version"]) == ("recorded", "v1")
    assert snapshot["scan_id"] == scan
    assert frameworks[overview_catalog["unassessed"]]["snapshot"] is None
    assert not {overview_catalog["draft"], overview_catalog["retired"]} & frameworks.keys()


def test_recent_scans_are_bounded_and_all_dashboard_data_is_tenant_scoped(
    client: TestClient, superuser: Engine, overview_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    other, other_subs = org_with(client, superuser)
    add_snapshot(superuser, other, overview_catalog["active"])
    ids = []
    with superuser.begin() as conn:
        for index in range(7):
            scan_id = str(uuid.uuid4())
            ids.append(scan_id)
            conn.execute(
                text(
                    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger,"
                    " status, engine, engine_version, expected_checks, evaluated_checks, queued_at)"
                    " VALUES (:id, :org, :connection, 'm365', 'user', :status, 'prowler', '5.49.0',"
                    " 10, 7, :at)"
                ),
                {
                    "id": scan_id,
                    "org": org,
                    "connection": str(uuid.uuid4()),
                    "status": "partial" if index % 2 else "failed",
                    "at": datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
                },
            )
        conn.execute(
            text(
                "INSERT INTO evidence (id, organization_id, kind, title, source_type, created_by,"
                " collected_at) VALUES (:id, :org, 'attestation', 'Synthetic evidence',"
                " 'upload', :author, now())"
            ),
            {"id": str(uuid.uuid4()), "org": org, "author": str(uuid.uuid4())},
        )
    data = client.get(f"/api/v1/orgs/{org}/overview", headers=auth(subs["owner"])).json()
    assert [s["id"] for s in data["scans"]] == list(reversed(ids))[:5]
    assert all((s["evaluated_checks"], s["expected_checks"]) == (7, 10) for s in data["scans"])
    assert data["evidence_count"] == 1
    assert (
        next(f for f in data["frameworks"] if f["key"] == overview_catalog["active"])["snapshot"]
        is None
    )
    other_data = client.get(
        f"/api/v1/orgs/{other}/overview", headers=auth(other_subs["owner"])
    ).json()
    assert other_data["scans"] == []
    assert other_data["evidence_count"] == 0
    forbidden = {"storage_key", "output_prefix", "manifest_sha256", "connection_id", "error_code"}
    assert all(not forbidden & scan.keys() for scan in data["scans"])


def test_snapshot_ties_are_deterministic_and_zero_is_not_missing(
    client: TestClient, superuser: Engine, overview_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    key = overview_catalog["active"]
    ids = sorted([str(uuid.uuid4()), str(uuid.uuid4())])
    add_snapshot(superuser, org, key, id=ids[0])
    add_snapshot(superuser, org, key, id=ids[1], score=0, passed=0)
    data = client.get(f"/api/v1/orgs/{org}/overview", headers=auth(subs["owner"])).json()
    snapshot = next(f for f in data["frameworks"] if f["key"] == key)["snapshot"]
    assert snapshot["id"] == ids[1]
    assert snapshot["score"] == 0


def test_draft_gate_and_development_label_follow_runtime_configuration(
    client: TestClient,
    superuser: Engine,
    overview_catalog: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, subs = org_with(client, superuser)
    url = f"/api/v1/orgs/{org}/overview"
    monkeypatch.setenv("ATESTA_ENV", "test")
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    data = client.get(url, headers=auth(subs["owner"])).json()
    keys = {f["key"] for f in data["frameworks"]}
    assert data["development"] is True
    assert overview_catalog["draft"] in keys
    assert overview_catalog["retired"] not in keys
    monkeypatch.delenv("ATESTA_CATALOG_INCLUDE_DRAFTS")
    monkeypatch.setenv("ATESTA_ENV", "production")
    data = client.get(url, headers=auth(subs["owner"])).json()
    assert data["development"] is False
    assert overview_catalog["draft"] not in {f["key"] for f in data["frameworks"]}
