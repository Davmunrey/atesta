"""Requirement register and statement of applicability (requirement-register spec), on real
PostgreSQL with RLS."""

import csv
import io
import json
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from .conftest import auth
from .test_members import events, org_with
from .test_overview import overview_catalog as overview_catalog

CATEGORY = {
    "selection_basis": "categoría · Todas",
    "selection_rules": [
        {"level": "BÁSICA", "rule": "n.a."},
        {"level": "MEDIA", "rule": "aplica"},
        {"level": "ALTA", "rule": "+ R1"},
    ],
}
DIMENSION = {
    "selection_basis": "nivel · C T",
    "selection_rules": [
        {"level": "BAJO", "rule": "aplica"},
        {"level": "MEDIO", "rule": "+ R1"},
        {"level": "ALTO", "rule": "+ R1+R2"},
    ],
}
SCOPE = {"categoría": "MEDIA", "nivel": {"C": "BAJO", "T": "MEDIO"}}


@pytest.fixture
def pack(superuser: Engine, overview_catalog: dict[str, str]) -> Iterator[str]:
    key = overview_catalog["active"]
    with superuser.begin() as conn:
        for code, attributes in (("m.cat", CATEGORY), ("m.dim", DIMENSION), ("m.none", {})):
            conn.execute(
                text(
                    "INSERT INTO requirements (framework_key, code, title_es, title_en, source,"
                    " attributes) VALUES (:k, :c, 'Medida sintética', NULL, 'synthetic',"
                    " CAST(:a AS jsonb))"
                ),
                {"k": key, "c": code, "a": json.dumps(attributes)},
            )
    yield key
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM requirements WHERE framework_key = :k"), {"k": key})


def base(org: str, framework: str) -> str:
    return f"/api/v1/orgs/{org}/frameworks/{framework}"


def assessment(**changes: Any) -> dict[str, Any]:
    return {
        "applicability": "applies",
        "implementation": "implemented",
        "regularly_reviewed": True,
        "performed_by": "Responsable de sistemas",
        "performed_on": "2026-11-20",
        "notes": "Revisado en el comité de seguridad.",
        **changes,
    }


def _scoped(client: TestClient, superuser: Engine, pack: str) -> tuple[str, dict[str, str]]:
    org, subs = org_with(client, superuser, ana="member")
    response = client.post(
        base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=auth(subs["owner"])
    )
    assert response.status_code == 201, response.text
    return org, subs


def test_scope_proposals_follow_the_pack_rules(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    register = client.get(base(org, pack) + "/register", headers=auth(subs["ana"])).json()
    proposals = {item["code"]: item["proposal"] for item in register["items"]}
    assert proposals["m.cat"] == {"decision": "applies", "rule": "aplica", "level": "MEDIA"}
    # C is BAJO and T is MEDIO: the highest listed dimension decides.
    assert proposals["m.dim"] == {"decision": "applies", "rule": "+ R1", "level": "MEDIO"}
    assert proposals["m.none"]["decision"] == "undecided"
    assert register["axes"]["categoría"]["levels"] == ["BÁSICA", "MEDIA", "ALTA"]
    assert events(superuser, org, "framework.scope_recorded") == 1


def test_a_scope_with_undeclared_levels_is_refused(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser)
    for bad in ({"categoría": "MEDIUM"}, {"nivel": {"Z": "ALTO"}}, {"other": "x"}):
        response = client.post(
            base(org, pack) + "/scope", json={"axis_values": bad}, headers=auth(subs["owner"])
        )
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "compliance.scope_invalid"


def test_an_admin_records_an_assessment_and_members_read_it(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    url = base(org, pack) + "/register/m.cat"
    assert client.post(url, json=assessment(), headers=auth(subs["ana"])).status_code == 403
    response = client.post(url, json=assessment(), headers=auth(subs["owner"]))
    assert response.status_code == 201, response.text
    item = next(
        i
        for i in client.get(base(org, pack) + "/register", headers=auth(subs["ana"])).json()[
            "items"
        ]
        if i["code"] == "m.cat"
    )
    assert item["assessment"]["implementation"] == "implemented"
    assert item["assessment"]["performed_by"] == "Responsable de sistemas"


def test_a_decision_against_the_proposal_needs_a_justification(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    url = base(org, pack) + "/register/m.cat"  # the proposal is "applies"
    refused = client.post(
        url, json=assessment(applicability="not_applicable"), headers=auth(subs["owner"])
    )
    assert refused.status_code == 422
    assert refused.json()["detail"]["code"] == "compliance.justification_required"
    accepted = client.post(
        url,
        json=assessment(
            applicability="not_applicable", justification="El sistema no presta ese servicio."
        ),
        headers=auth(subs["owner"]),
    )
    assert accepted.status_code == 201, accepted.text


def test_evidence_from_another_organization_is_refused(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    response = client.post(
        base(org, pack) + "/register/m.cat",
        json=assessment(evidence_statement_ids=[str(uuid.uuid4())]),
        headers=auth(subs["owner"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "compliance.evidence_not_found"


def test_an_unknown_requirement_or_framework_is_not_found(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    headers = auth(subs["owner"])
    assert (
        client.post(
            base(org, pack) + "/register/nope", json=assessment(), headers=headers
        ).status_code
        == 404
    )
    assert client.get(base(org, "nope") + "/register", headers=headers).status_code == 404


def test_audit_metadata_carries_no_free_text(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    secret = "Texto del cliente que no debe salir del registro"
    client.post(
        base(org, pack) + "/register/m.cat",
        json=assessment(notes=secret, performed_by="Ana"),
        headers=auth(subs["owner"]),
    )
    client.post(
        base(org, pack) + "/assessment-reviews",
        json={
            "reviewer_name": "Ana",
            "reviewer_role": "Responsable de la seguridad",
            "reviewed_on": "2026-11-21",
            "conclusions": secret,
            "corrective_actions": secret,
        },
        headers=auth(subs["owner"]),
    )
    with superuser.connect() as conn:
        rows = conn.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE organization_id = :o"),
            {"o": org},
        ).all()
    actions = {action for action, _ in rows}
    assert {"requirement.assessed", "framework.assessment_reviewed"} <= actions
    assert all(secret not in metadata and "Ana" not in metadata for _, metadata in rows)


def test_the_review_is_recorded_and_listed(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    review = {
        "reviewer_name": "Ana Pérez",
        "reviewer_role": "Responsable de la seguridad",
        "reviewed_on": "2026-11-21",
        "conclusions": "Autoevaluación revisada.",
        "corrective_actions": "Completar op.exp.2 antes de marzo.",
    }
    url = base(org, pack) + "/assessment-reviews"
    assert client.post(url, json=review, headers=auth(subs["ana"])).status_code == 403
    assert client.post(url, json=review, headers=auth(subs["owner"])).status_code == 201
    listed = client.get(url, headers=auth(subs["ana"])).json()
    assert [r["reviewer_role"] for r in listed] == ["Responsable de la seguridad"]
    register = client.get(base(org, pack) + "/register", headers=auth(subs["ana"])).json()
    assert register["review"]["conclusions"] == "Autoevaluación revisada."


def test_the_statement_of_applicability_exports_every_requirement(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    client.post(
        base(org, pack) + "/register/m.dim",
        json=assessment(notes='=HYPERLINK("x")', justification="=cmd|' /C calc'!A0"),
        headers=auth(subs["owner"]),
    )
    statement = client.get(base(org, pack) + "/applicability", headers=auth(subs["ana"])).json()
    assert [r["code"] for r in statement["rows"]] == ["m.cat", "m.dim", "m.none"]
    assert "Not a certification" in statement["statement"]
    assert set(statement["signer"].values()) == {None}
    assert [r["decided_by_person"] for r in statement["rows"]] == [False, True, False]

    response = client.get(base(org, pack) + "/applicability.csv", headers=auth(subs["ana"]))
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text)))
    header = next(i for i, row in enumerate(rows) if row and row[0] == "Código")
    data = rows[header + 1 :]
    assert len(data) == 3
    assert all(not cell.startswith(("=", "+", "-", "@")) for row in data for cell in row)
    assert events(superuser, org, "framework.applicability_exported") == 2


def test_recording_assessments_never_changes_a_score(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    client.post(base(org, pack) + "/register/m.cat", json=assessment(), headers=auth(subs["owner"]))
    with superuser.connect() as conn:
        snapshots = conn.execute(
            text("SELECT count(*) FROM score_snapshots WHERE organization_id = :o"), {"o": org}
        ).scalar_one()
        jobs = conn.execute(
            text("SELECT count(*) FROM procrastinate_jobs WHERE args->>'organization_id' = :o"),
            {"o": org},
        ).scalar_one()
    assert (snapshots, jobs) == (0, 0)


@pytest.mark.parametrize("table", ["framework_scopes", "requirement_assessments"])
def test_register_rows_are_append_only(
    client: TestClient, superuser: Engine, app_engine: Engine, pack: str, table: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    client.post(base(org, pack) + "/register/m.cat", json=assessment(), headers=auth(subs["owner"]))
    with app_engine.connect() as conn:
        tx = conn.begin()
        conn.execute(text("SELECT set_config('app.organization_id', :o, true)"), {"o": org})
        with pytest.raises(DBAPIError):
            conn.execute(text(f"UPDATE {table} SET framework_key = 'x'"))  # noqa: S608 - fixed names  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text - fixed table names, no user input
        tx.rollback()


# --- insights: owners, history, trend, activity (insights spec) ------------------------------


def _uid(client: TestClient, sub: str) -> str:
    return str(client.get("/api/v1/me", headers=auth(sub)).json()["id"])


def test_an_admin_assigns_an_owner_and_a_due_date_and_can_clear_them(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    ana = _uid(client, subs["ana"])
    url = base(org, pack) + "/register/m.cat/assignment"
    body = {"owner_user_id": ana, "due_on": "2026-12-31"}
    assert client.post(url, json=body, headers=auth(subs["ana"])).status_code == 403
    assert client.post(url, json=body, headers=auth(subs["owner"])).status_code == 201
    items = client.get(base(org, pack) + "/register", headers=auth(subs["ana"])).json()["items"]
    item = next(i for i in items if i["code"] == "m.cat")
    assert (item["assignment"]["owner_user_id"], item["assignment"]["due_on"]) == (
        ana,
        "2026-12-31",
    )
    cleared = {"owner_user_id": None, "due_on": None}
    assert client.post(url, json=cleared, headers=auth(subs["owner"])).status_code == 201
    items = client.get(base(org, pack) + "/register", headers=auth(subs["ana"])).json()["items"]
    assert next(i for i in items if i["code"] == "m.cat")["assignment"] is None
    with superuser.connect() as conn:
        details = (
            conn.execute(
                text(
                    "SELECT metadata::text FROM audit_events WHERE organization_id = :o"
                    " AND action = 'requirement.assigned'"
                ),
                {"o": org},
            )
            .scalars()
            .all()
        )
    assert len(details) == 2 and all("@" not in d for d in details)


def test_only_a_member_of_the_organization_can_own_a_requirement(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    _, outsider_subs = org_with(client, superuser)
    outsider = _uid(client, outsider_subs["owner"])
    response = client.post(
        base(org, pack) + "/register/m.cat/assignment",
        json={"owner_user_id": outsider},
        headers=auth(subs["owner"]),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "compliance.owner_not_member"


def test_history_replays_assessments_day_by_day(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    owner = _uid(client, subs["owner"])
    with superuser.begin() as conn:
        for code, days_ago, implementation in (
            ("m.cat", 3, "not_implemented"),
            ("m.cat", 1, "implemented"),
            ("m.dim", 2, "partially_implemented"),
        ):
            conn.execute(
                text(
                    "INSERT INTO requirement_assessments (id, organization_id, framework_key,"
                    " requirement_code, applicability, implementation, regularly_reviewed,"
                    " recorded_by, recorded_at) VALUES (gen_random_uuid(), :o, :f, :c, 'applies',"
                    " :i, false, :u, now() - make_interval(days => :d))"
                ),
                {"o": org, "f": pack, "c": code, "i": implementation, "u": owner, "d": days_ago},
            )
    points = client.get(base(org, pack) + "/register/history", headers=auth(subs["ana"])).json()
    assert len(points) == 4
    assert [p["assessed"] for p in points] == [1, 2, 2, 2]
    assert [p["implemented"] for p in points] == [0, 0, 1, 1]


def test_trend_is_empty_without_recorded_snapshots(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    assert client.get(base(org, pack) + "/trend", headers=auth(subs["ana"])).json() == []


def test_activity_is_for_admins_and_carries_no_metadata(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = _scoped(client, superuser, pack)
    client.post(
        base(org, pack) + "/register/m.cat",
        json=assessment(notes="Texto privado del cliente"),
        headers=auth(subs["owner"]),
    )
    url = f"/api/v1/orgs/{org}/activity"
    assert client.get(url, headers=auth(subs["ana"])).status_code == 403
    activity = client.get(url, headers=auth(subs["owner"])).json()
    assert activity["days"] == 30 and len(activity["daily"]) == 31
    assert sum(d["count"] for d in activity["daily"]) >= 3  # org created, scope, assessment
    actions = {e["action"] for e in activity["events"]}
    assert {"org.created", "framework.scope_recorded", "requirement.assessed"} <= actions
    assert all(
        set(e) == {"occurred_at", "actor_email", "action", "target_type", "target_id"}
        for e in activity["events"]
    )
    assert any(e["actor_email"] for e in activity["events"])
    assert "Texto privado" not in str(activity)
    ninety = client.get(url + "?days=90", headers=auth(subs["owner"]))
    assert ninety.status_code == 200 and len(ninety.json()["daily"]) == 91  # a real query string
    assert client.get(url + "?days=30", headers=auth(subs["owner"])).status_code == 200
    assert client.get(url + "?days=7", headers=auth(subs["owner"])).status_code == 422
