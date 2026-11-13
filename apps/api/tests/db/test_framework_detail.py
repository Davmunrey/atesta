"""Read-only framework register, using real PostgreSQL and synthetic catalog data."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth, new_sub
from .test_members import org_with
from .test_overview import add_snapshot
from .test_overview import overview_catalog as overview_catalog


@pytest.fixture
def detail_catalog(superuser: Engine, overview_catalog: dict[str, str]) -> Iterator[dict[str, str]]:
    key = overview_catalog["active"]
    control = f"detail_{uuid.uuid4().hex}"
    with superuser.begin() as conn:
        for code in ("R1", "R2", "R3"):
            conn.execute(
                text(
                    "INSERT INTO requirements (framework_key, code, title_es, title_en, source)"
                    " VALUES (:key, :code, 'Requisito sintético',"
                    " 'Synthetic requirement', 'synthetic')"
                ),
                {"key": key, "code": code},
            )
        conn.execute(
            text(
                "INSERT INTO controls (key, title_es, title_en, description_es, description_en,"
                " remediation_refs) VALUES (:control, 'Configuración sintética',"
                " 'Synthetic setting', 'Revisa el registro de prueba.',"
                " 'Review the test record.', ARRAY['synthetic guide'])"
            ),
            {"control": control},
        )
        conn.execute(
            text(
                "INSERT INTO mappings"
                " (framework_key, requirement_code, control_key, rationale, source)"
                " VALUES (:key, 'R1', :control, 'synthetic rationale', 'synthetic source')"
            ),
            {"key": key, "control": control},
        )
    yield {**overview_catalog, "control": control}
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM control_checks WHERE control_key = :key"), {"key": control})
        conn.execute(text("DELETE FROM mappings WHERE framework_key = :key"), {"key": key})
        conn.execute(text("DELETE FROM requirements WHERE framework_key = :key"), {"key": key})
        conn.execute(text("DELETE FROM controls WHERE key = :key"), {"key": control})


def url(org: str, key: str) -> str:
    return f"/api/v1/orgs/{org}/frameworks/{key}"


def test_preparation_context_is_allowlisted_and_never_an_assessment(
    client: TestClient, superuser: Engine, detail_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    key = detail_catalog["active"]
    context = {
        "content_state": "partial",
        "assessment_enabled": False,
        "summary_es": "Ejemplo",
        "summary_en": "Example",
        "scope_es": "Alcance de prueba",
        "scope_en": "Test scope",
        "applicability_es": "Revisión humana",
        "applicability_en": "Human review",
        "limitations_es": "Sin revisar",
        "limitations_en": "Unreviewed",
        "preparation_controls": [detail_catalog["control"], "missing"],
        "source_refs": ["https://example.test/source"],
        "verified_on": "2026-11-13",
        "private_note": "not public",
        "preview_fingerprint": "not public",
    }
    guidance = {
        "official_text_es": "Texto sintético de prueba.",
        "applicability_es": "Depende del alcance.",
        "selection_basis": "dimension",
        "selection_rules": [{"level": "low", "rule": "example"}],
        "section": "1.2",
        "source_sha256": "a" * 64,
        "private_note": "not public",
    }
    with superuser.begin() as conn:
        conn.execute(
            text("UPDATE frameworks SET attributes = CAST(:data AS jsonb) WHERE key = :key"),
            {"key": key, "data": json.dumps(context)},
        )
        conn.execute(
            text(
                "UPDATE requirements SET attributes = CAST(:data AS jsonb)"
                " WHERE framework_key = :key AND code = 'R1'"
            ),
            {"key": key, "data": json.dumps(guidance)},
        )
    response = client.get(url(org, key), headers=auth(subs["owner"]))
    assert response.status_code == 200
    data = response.json()
    assert data["catalog_context"]["assessment_enabled"] is False
    assert data["requirements"][0]["guidance"]["selection_rules"] == guidance["selection_rules"]
    assert data["requirements"][1]["guidance"] is None
    assert [c["key"] for c in data["preparation_controls"]] == [detail_catalog["control"]]
    assert data["preparation_controls"][0]["checks"] == []
    assert "observed_status" not in data["preparation_controls"][0]
    assert "mapping_reviewed" not in data["preparation_controls"][0]
    assert "private_note" not in response.text and "preview_fingerprint" not in response.text
    assert data["snapshot"] is None
    assert {r["status"] for r in data["requirements"]} == {"not_evaluated"}


@pytest.mark.parametrize("role", ["owner", "admin", "member"])
def test_framework_detail_lists_catalog_without_inventing_results(
    client: TestClient, superuser: Engine, detail_catalog: dict[str, str], role: str
) -> None:
    org, subs = org_with(client, superuser, admin="admin", member="member")
    response = client.get(url(org, detail_catalog["active"]), headers=auth(subs[role]))
    assert response.status_code == 200
    data = response.json()
    assert data["snapshot"] is None
    assert data["catalog_matches_snapshot"] is False
    assert {r["status"] for r in data["requirements"]} == {"not_evaluated"}
    control = data["requirements"][0]["controls"][0]
    assert control["key"] == detail_catalog["control"]
    assert control["description_en"] == "Review the test record."
    assert control["observed_status"] is None
    assert control["mapping_reviewed"] is False
    assert control["remediation_refs"] == ["synthetic guide"]
    assert "reviewed_by" not in control


def test_framework_detail_gates_membership_and_catalog(
    client: TestClient, superuser: Engine, detail_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    assert client.get(url(org, detail_catalog["active"])).status_code == 401
    assert (
        client.get(url(org, detail_catalog["active"]), headers=auth(new_sub())).status_code == 404
    )
    for key in ("missing", detail_catalog["draft"], detail_catalog["retired"]):
        response = client.get(url(org, key), headers=auth(subs["owner"]))
        assert response.status_code == 404
        assert response.json() == {"detail": {"code": "compliance.not_found"}}


def test_framework_detail_preserves_history_and_labels_current_catalog(
    client: TestClient, superuser: Engine, detail_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    other, other_subs = org_with(client, superuser)
    key = detail_catalog["active"]
    original = add_snapshot(superuser, org, key, results='{"R1":"fail","R2":"manual","OLD":"pass"}')
    with superuser.begin() as conn:
        conn.execute(
            text(
                "UPDATE requirements SET retired_at = now()"
                " WHERE framework_key = :key AND code = 'R2'"
            ),
            {"key": key},
        )
    add_snapshot(superuser, org, key, scope=str(uuid.uuid4()), at=datetime(2026, 3, 1, tzinfo=UTC))
    data = client.get(url(org, key), headers=auth(subs["owner"])).json()
    assert data["snapshot"]["id"] == original
    assert data["catalog_matches_snapshot"] is False
    rows = {r["code"]: r for r in data["requirements"]}
    assert rows["R1"]["status"] == "fail"
    assert rows["R3"]["status"] == "not_evaluated"
    assert rows["R2"]["in_current_catalog"] is False
    assert rows["OLD"]["title_es"] is None
    assert rows["OLD"]["status"] == "pass"
    assert rows["OLD"]["controls"] == []
    isolated = client.get(url(other, key), headers=auth(other_subs["owner"])).json()
    assert isolated["snapshot"] is None
    assert "OLD" not in {r["code"] for r in isolated["requirements"]}


def test_observations_use_snapshot_scan_time_and_never_another_tenant(
    client: TestClient, superuser: Engine, detail_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    other, _ = org_with(client, superuser)
    key, control = detail_catalog["active"], detail_catalog["control"]
    check = f"check_{uuid.uuid4().hex}"
    first, later, foreign = [str(uuid.uuid4()) for _ in range(3)]
    connection = str(uuid.uuid4())
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO checks (engine, check_id, engine_version)"
                " VALUES ('prowler', :check, '5.49.0')"
            ),
            {"check": check},
        )
        conn.execute(
            text(
                "INSERT INTO control_checks (control_key, engine, check_id)"
                " VALUES (:control, 'prowler', :check)"
            ),
            {"control": control, "check": check},
        )
        for scan, tenant, day, state in (
            (first, org, 1, "fail"),
            (later, org, 3, "pass"),
            (foreign, other, 1, "manual"),
        ):
            conn.execute(
                text(
                    "INSERT INTO scans (id, organization_id, connection_id, provider, trigger,"
                    " status, engine, engine_version, ingested_at) VALUES (:id, :org, :connection,"
                    " 'm365', 'user', 'succeeded', 'prowler', '5.49.0', :at)"
                ),
                {
                    "id": scan,
                    "org": tenant,
                    "connection": connection,
                    "at": datetime(2026, 1, day, tzinfo=UTC),
                },
            )
            conn.execute(
                text(
                    "INSERT INTO scan_check_results"
                    " (organization_id, scan_id, engine, check_id, status)"
                    " VALUES (:org, :scan, 'prowler', :check, :state)"
                ),
                {"org": tenant, "scan": scan, "check": check, "state": state},
            )
    original = add_snapshot(
        superuser,
        org,
        key,
        scan=first,
        framework_version="current",
        catalog_version="v2",
        results='{"R1":"fail"}',
    )
    response = client.get(url(org, key), headers=auth(subs["owner"]))
    assert response.status_code == 200
    data = response.json()
    assert data["catalog_matches_snapshot"] is True
    configuration = data["requirements"][0]["controls"][0]
    assert configuration["observed_status"] == "fail"
    assert configuration["checks"] == [
        {"engine": "prowler", "check_id": check, "observed_status": "fail"}
    ]
    correction = add_snapshot(
        superuser,
        org,
        key,
        scan=first,
        supersedes=original,
        at=datetime(2026, 2, 1, tzinfo=UTC),
        score=0,
        results='{"R1":"manual"}',
    )
    corrected = client.get(url(org, key), headers=auth(subs["owner"])).json()
    assert corrected["snapshot"]["id"] == correction
    assert corrected["snapshot"]["score"] == 0
    assert corrected["requirements"][0]["status"] == "manual"
    assert corrected["requirements"][0]["controls"][0]["observed_status"] is None
    assert corrected["requirements"][0]["controls"][0]["checks"][0]["observed_status"] is None
    with superuser.begin() as conn:
        conn.execute(text("UPDATE controls SET manual = true WHERE key = :key"), {"key": control})
    manual = client.get(url(org, key), headers=auth(subs["owner"])).json()
    assert manual["requirements"][0]["controls"][0]["checks"] == []


def test_missing_scan_is_not_passing_and_development_gate_is_explicit(
    client: TestClient,
    superuser: Engine,
    detail_catalog: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, subs = org_with(client, superuser)
    key = detail_catalog["active"]
    add_snapshot(
        superuser,
        org,
        key,
        framework_version="current",
        catalog_version="v2",
        results='{"R1":"manual"}',
        score=None,
    )
    data = client.get(url(org, key), headers=auth(subs["owner"])).json()
    assert data["snapshot"]["score"] is None
    assert data["requirements"][0]["controls"][0]["observed_status"] is None
    monkeypatch.setenv("ATESTA_ENV", "test")
    monkeypatch.setenv("ATESTA_CATALOG_INCLUDE_DRAFTS", "true")
    draft = client.get(url(org, detail_catalog["draft"]), headers=auth(subs["owner"]))
    assert draft.status_code == 200
    assert draft.json()["development"] is True
