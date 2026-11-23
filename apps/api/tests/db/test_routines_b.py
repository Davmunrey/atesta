"""Recorded routines, part B (recorded-routines spec): training links and incident clocks, on
real PostgreSQL with RLS."""

import json
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta

import pytest
from atesta_api.modules.compliance import training
from atesta_api.modules.identity.api import enter_training_link_context, token_hash
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_members import events, org_with
from .test_rbac import _add, _future
from .test_routines import _statements

CLOCKS = [
    {"key": "early", "title_es": "Alerta temprana", "title_en": "Early warning", "hours": 24,
     "needs": "significant", "requirement": "r1"},
    {"key": "notice", "title_es": "Notificación", "title_en": "Notification", "hours": 72,
     "needs": "significant", "requirement": "r2"},
    {"key": "final", "title_es": "Informe final", "title_en": "Final report", "months": 1,
     "after": "notice", "needs": "significant", "requirement": "r3"},
    {"key": "breach", "title_es": "Violación de datos", "title_en": "Breach", "hours": 72,
     "needs": "personal_data", "requirement": "r4"},
]  # fmt: skip


@pytest.fixture
def clock_pack(superuser: Engine) -> Iterator[str]:
    key = f"clocks_{uuid.uuid4().hex}"
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes,"
                " status, attributes, catalog_version) VALUES (:k, 'Synthetic', '1', 'EU',"
                " 'synthetic', 'test', 'released', CAST(:a AS jsonb), 'v1')"
            ),
            {"k": key, "a": json.dumps({"reporting_clocks": CLOCKS})},
        )
    yield key
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM frameworks WHERE key = :k"), {"k": key})


# --- training ------------------------------------------------------------------------------


def _campaign(client: TestClient, org: str, sub: str) -> tuple[dict, str]:  # type: ignore[type-arg]  # JSON body
    body = {
        "title": "Phishing 2026",
        "material_url": "https://example.com/phishing.pdf",
        "closes_on": (date.today() + timedelta(days=14)).isoformat(),
    }
    response = client.post(f"/api/v1/orgs/{org}/training-campaigns", json=body, headers=auth(sub))
    assert response.status_code == 201, response.text
    created = response.json()
    prefix = "https://app.example.com/training#token="
    assert created["link"].startswith(prefix)
    return created, created["link"].removeprefix(prefix)


def _ack(client: TestClient, token: str, email: str, name: str = "Ana Pérez") -> object:
    return client.post(
        "/api/v1/training/acknowledge",
        json={"token": token, "full_name": name, "email": email},
    )


def test_people_confirm_through_the_link_and_closing_leaves_evidence(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    campaign, token = _campaign(client, org, subs["owner"])
    link = client.post("/api/v1/training/link", json={"token": token})
    assert link.status_code == 200, link.text
    assert link.json()["title"] == "Phishing 2026"
    first = _ack(client, token, "ana@example.com")
    assert (first.status_code, first.json()) == (200, {"recorded": True})  # type: ignore[attr-defined]
    again = _ack(client, token, "ANA@example.com", "Someone else")
    assert again.json() == {"recorded": False}  # type: ignore[attr-defined]
    url = f"/api/v1/orgs/{org}/training-campaigns/{campaign['id']}"
    detail = client.get(url, headers=auth(subs["ana"])).json()
    assert detail["acknowledged"] == 1
    assert [(a["full_name"], a["email"]) for a in detail["acknowledgements"]] == [
        ("Ana Pérez", "ana@example.com")
    ]
    assert client.post(url + "/close", headers=auth(subs["ana"])).status_code == 403
    closed = client.post(url + "/close", headers=auth(subs["owner"]))
    assert closed.status_code == 200, closed.text
    assert closed.json()["closed_at"]
    assert client.post(url + "/close", headers=auth(subs["owner"])).status_code == 409
    late = _ack(client, token, "luis@example.com")
    assert late.status_code == 410  # type: ignore[attr-defined]
    assert late.json()["detail"]["code"] == "compliance.training_closed"  # type: ignore[attr-defined]
    statements = _statements(superuser, org, "ctl.people_awareness")
    assert len(statements) == 1
    assert "Formación «Phishing 2026». Confirmaciones de lectura: 1." in statements[0]
    assert events(superuser, org, "training.acknowledged") == 1
    assert events(superuser, org, "training.closed") == 1


def test_the_public_link_refuses_what_it_should(
    client: TestClient, superuser: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, subs = org_with(client, superuser)
    campaign, token = _campaign(client, org, subs["owner"])
    unknown = client.post("/api/v1/training/link", json={"token": "x" * 43})
    assert (unknown.status_code, unknown.json()["detail"]["code"]) == (
        404,
        "compliance.training_link_invalid",
    )
    in_query = client.post(f"/api/v1/training/link?token={token}", json={"token": token})
    assert in_query.status_code == 400
    bad_email = _ack(client, token, "not-an-email")
    assert bad_email.status_code == 422  # type: ignore[attr-defined]
    monkeypatch.setattr(training, "MAX_ACKNOWLEDGEMENTS", 2)
    assert _ack(client, token, "a@example.com").status_code == 200  # type: ignore[attr-defined]
    assert _ack(client, token, "b@example.com").status_code == 200  # type: ignore[attr-defined]
    full = _ack(client, token, "c@example.com")
    assert (full.status_code, full.json()["detail"]["code"]) == (409, "compliance.training_full")  # type: ignore[attr-defined]
    assert _ack(client, token, "a@example.com").json() == {"recorded": False}  # type: ignore[attr-defined]
    with superuser.begin() as conn:
        conn.execute(
            text("UPDATE training_campaigns SET closes_on = :d WHERE id = :i"),
            {"d": date.today() - timedelta(days=1), "i": campaign["id"]},
        )
    assert client.post("/api/v1/training/link", json={"token": token}).status_code == 410
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=auth(subs["owner"])).json()
    assert [(d["kind"], d["id"]) for d in due] == [("training_unclosed", campaign["id"])]


def test_campaign_input_and_roles(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser, ana="member")
    url = f"/api/v1/orgs/{org}/training-campaigns"
    body = {
        "title": "T",
        "material_url": "https://example.com/t",
        "closes_on": date.today().isoformat(),
    }
    assert client.post(url, json=body, headers=auth(subs["ana"])).status_code == 403
    for wrong in (
        {"material_url": "http://example.com/t"},
        {"closes_on": (date.today() - timedelta(days=1)).isoformat()},
    ):
        assert (
            client.post(url, json={**body, **wrong}, headers=auth(subs["owner"])).status_code == 422
        )
    assert client.post(url, json=body, headers=auth(subs["owner"])).status_code == 201
    assert len(client.get(url, headers=auth(subs["ana"])).json()) == 1


def test_a_link_reaches_only_its_own_campaign(
    client: TestClient, superuser: Engine, app_engine: Engine
) -> None:
    org_a, subs_a = org_with(client, superuser)
    org_b, subs_b = org_with(client, superuser)
    _, token_a = _campaign(client, org_a, subs_a["owner"])
    campaign_b, _ = _campaign(client, org_b, subs_b["owner"])
    assert _ack(client, token_a, "ana@example.com").status_code == 200  # type: ignore[attr-defined]
    detail_b = client.get(
        f"/api/v1/orgs/{org_b}/training-campaigns/{campaign_b['id']}",
        headers=auth(subs_b["owner"]),
    ).json()
    assert detail_b["acknowledged"] == 0
    with app_engine.connect() as conn, conn.begin():
        from sqlalchemy.orm import Session

        session = Session(bind=conn)
        enter_training_link_context(session, token_hash(token_a))
        seen = session.execute(text("SELECT organization_id FROM training_campaigns")).scalars()
        assert [str(o) for o in seen] == [org_a]
        changed = session.execute(text("UPDATE training_campaigns SET title = 'x'"))
        assert changed.rowcount == 0  # type: ignore[attr-defined]  # the link policy reads only
        assert session.execute(text("SELECT count(*) FROM training_acknowledgements")).scalar() == 0
        conn.rollback()


# --- incidents ----------------------------------------------------------------------------


def _incident(client: TestClient, org: str, sub: str, hours_ago: float, **flags: bool) -> dict:  # type: ignore[type-arg]  # JSON body
    body = {
        "title": "Ransomware en el servidor de ficheros",
        "aware_at": (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat(),
        "significant": flags.get("significant", False),
        "personal_data": flags.get("personal_data", False),
    }
    response = client.post(f"/api/v1/orgs/{org}/incidents", json=body, headers=auth(sub))
    assert response.status_code == 201, response.text
    return response.json()


def test_incident_clocks_run_from_pack_content_and_closing_leaves_evidence(
    client: TestClient, superuser: Engine, clock_pack: str
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    incident = _incident(client, org, subs["ana"], 30, significant=True, personal_data=True)
    mine = {
        c["ref"].split(":")[1]: c for c in incident["clocks"] if c["ref"].startswith(clock_pack)
    }
    assert {k: c["state"] for k, c in mine.items()} == {
        "early": "overdue",
        "notice": "running",
        "final": "waiting",
        "breach": "running",
    }
    assert incident["overdue"] >= 1
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=auth(subs["ana"])).json()
    first = due[0]
    assert (first["kind"], first["overdue"], first["clock"]["es"]) == (
        "incident_clock",
        True,
        "Alerta temprana",
    )
    url = f"/api/v1/orgs/{org}/incidents/{incident['id']}/updates"
    waiting = client.post(
        url, json={"kind": "clock", "clock": f"{clock_pack}:final"}, headers=auth(subs["ana"])
    )
    assert waiting.json()["detail"]["code"] == "compliance.clock_waiting"
    met = client.post(
        url, json={"kind": "clock", "clock": f"{clock_pack}:notice"}, headers=auth(subs["ana"])
    )
    assert met.status_code == 201, met.text
    clocks = {
        c["ref"].split(":")[1]: c for c in met.json()["clocks"] if c["ref"].startswith(clock_pack)
    }
    assert (clocks["notice"]["state"], clocks["notice"]["late"]) == ("met", False)
    assert clocks["final"]["state"] == "running"
    twice = client.post(
        url, json={"kind": "clock", "clock": f"{clock_pack}:notice"}, headers=auth(subs["ana"])
    )
    assert twice.json()["detail"]["code"] == "compliance.clock_met"
    unknown = client.post(url, json={"kind": "clock", "clock": "nope:x"}, headers=auth(subs["ana"]))
    assert unknown.status_code == 422
    note = client.post(url, json={"kind": "note", "note": "Aislado"}, headers=auth(subs["ana"]))
    assert note.status_code == 201
    closed = client.post(url, json={"kind": "closed"}, headers=auth(subs["ana"]))
    assert closed.status_code == 201, closed.text
    assert closed.json()["closed_at"] and closed.json()["next_due_at"] is None
    after = client.post(url, json={"kind": "note", "note": "x"}, headers=auth(subs["ana"]))
    assert after.json()["detail"]["code"] == "compliance.incident_closed"
    statements = _statements(superuser, org, "ctl.incident_response")
    assert len(statements) == 1
    assert "Incidente «Ransomware en el servidor de ficheros»." in statements[0]
    assert "Notificación (Synthetic): registrado el " in statements[0]
    assert "dentro de plazo." in statements[0]
    assert "Alerta temprana (Synthetic): sin registrar." in statements[0]
    due = client.get(f"/api/v1/orgs/{org}/routines/due", headers=auth(subs["ana"])).json()
    assert [d for d in due if d["kind"] == "incident_clock"] == []
    assert events(superuser, org, "incident.clock_met") == 1
    assert events(superuser, org, "incident.closed") == 1


def test_clocks_follow_the_flags(client: TestClient, superuser: Engine, clock_pack: str) -> None:
    org, subs = org_with(client, superuser)
    plain = _incident(client, org, subs["owner"], 1)
    assert [c for c in plain["clocks"] if c["ref"].startswith(clock_pack)] == []
    data = _incident(client, org, subs["owner"], 1, personal_data=True)
    assert [c["ref"] for c in data["clocks"] if c["ref"].startswith(clock_pack)] == [
        f"{clock_pack}:breach"
    ]
    listed = client.get(f"/api/v1/orgs/{org}/incidents", headers=auth(subs["owner"])).json()
    assert len(listed) == 2 and "clocks" not in listed[0]


def test_incident_input_and_roles(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    url = f"/api/v1/orgs/{org}/incidents"
    body = {
        "title": "X",
        "aware_at": datetime.now(UTC).isoformat(),
        "significant": False,
        "personal_data": False,
    }
    auditor = _add(superuser, client, org, "auditor", _future())
    assert client.post(url, json=body, headers=auth(auditor)).status_code == 403
    future = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    naive = datetime.now().replace(tzinfo=None).isoformat()
    for wrong in ({"aware_at": future}, {"aware_at": naive}, {"title": " "}):
        assert (
            client.post(url, json={**body, **wrong}, headers=auth(subs["owner"])).status_code == 422
        )
    created = client.post(url, json=body, headers=auth(subs["owner"])).json()
    updates = f"{url}/{created['id']}/updates"
    assert (
        client.post(updates, json={"kind": "note"}, headers=auth(subs["owner"])).status_code == 422
    )
    assert client.get(f"{url}/{created['id']}", headers=auth(auditor)).status_code == 200
    other, other_subs = org_with(client, superuser)
    assert (
        client.get(
            f"/api/v1/orgs/{other}/incidents/{created['id']}", headers=auth(other_subs["owner"])
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    ("table", "expected"),
    [
        ("training_campaigns", {"SELECT", "INSERT", "UPDATE"}),
        ("training_acknowledgements", {"SELECT", "INSERT"}),
        ("incidents", {"SELECT", "INSERT"}),
        ("incident_updates", {"SELECT", "INSERT"}),
    ],
)
def test_part_b_grants(superuser: Engine, table: str, expected: set[str]) -> None:
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


def test_the_incident_form_reads_the_official_criteria_of_active_packs(
    client: TestClient, superuser: Engine
) -> None:
    key = f"criteria_{uuid.uuid4().hex}"
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes,"
                " status, attributes, catalog_version) VALUES (:k, 'Synthetic', '1', 'EU',"
                " 'synthetic', 'test', 'released', CAST(:a AS jsonb), 'v1')"
            ),
            {
                "k": key,
                "a": json.dumps(
                    {"incident_criteria": [{"needs": "significant", "requirement": "r1"}]}
                ),
            },
        )
        conn.execute(
            text(
                "INSERT INTO requirements"
                " (framework_key, code, title_es, title_en, source, attributes)"
                " VALUES (:k, 'r1', 'Apartado 3', 'Paragraph 3', 'https://example.test/r1',"
                " CAST(:a AS jsonb))"
            ),
            {
                "k": key,
                "a": json.dumps(
                    {
                        "official_text_es": "Se considerará significativo…",
                        "official_text_en": "Significant if…",
                    }
                ),
            },
        )
    try:
        org, subs = org_with(client, superuser)
        found = client.get(f"/api/v1/orgs/{org}/incidents/criteria", headers=auth(subs["owner"]))
        assert found.status_code == 200, found.text
        mine = [c for c in found.json() if c["framework_key"] == key]
        assert mine == [
            {
                "needs": "significant",
                "framework_key": key,
                "framework_name": "Synthetic",
                "requirement": "r1",
                "title_es": "Apartado 3",
                "title_en": "Paragraph 3",
                "text_es": "Significativo si…",
                "text_en": "Significant if…",
                "source": "https://example.test/r1",
            }
        ]
    finally:
        with superuser.begin() as conn:
            conn.execute(text("DELETE FROM requirements WHERE framework_key = :k"), {"k": key})
            conn.execute(text("DELETE FROM frameworks WHERE key = :k"), {"k": key})
