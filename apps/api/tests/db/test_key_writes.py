"""Routine write routes for API keys (mcp-server spec, #333), on real PostgreSQL with RLS.

A key with routines:write records incidents and their updates, starts training campaigns and
access reviews. The author is the admin who owns the key; every write is audited with the key.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .test_api_keys_v2 import READ, bearer, make_key
from .test_members import org_with, uid

AWARE = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
WRITES = {
    "/api/v1/incidents": (
        {
            "title": "Caída del correo",
            "aware_at": AWARE,
            "significant": True,
            "personal_data": False,
        },
        "incident.created",
    ),
    "/api/v1/training-campaigns": (
        {
            "title": "Phishing 2026",
            "material_url": "https://example.test/curso",
            "closes_on": (date.today() + timedelta(days=30)).isoformat(),
        },
        "training.created",
    ),
    "/api/v1/access-reviews": (
        {
            "title": "Revisión trimestral",
            "system": "Microsoft 365",
            "accounts": [{"account": "ana"}],
        },
        "access_review.created",
    ),
}


def _audit(superuser: Engine, org: str, action: str) -> list[tuple[str, dict[str, object]]]:
    with superuser.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_user_id, metadata FROM audit_events"
                " WHERE organization_id = :o AND action = :a"
            ),
            {"o": org, "a": action},
        ).all()
    return [(str(r.actor_user_id), r.metadata) for r in rows]


@pytest.mark.parametrize("path", sorted(WRITES))
def test_each_routine_write_needs_its_scope_and_is_audited_with_the_key(
    client: TestClient, superuser: Engine, path: str
) -> None:
    org, subs = org_with(client, superuser)
    body, action = WRITES[path]
    reader = make_key(client, org, subs["owner"], [*READ, "evidence:write", "assessment:propose"])
    refused = client.post(path, json=body, headers=bearer(reader["token"]))
    assert (refused.status_code, refused.json()["detail"]["scope"]) == (403, "routines:write")
    writer = make_key(client, org, subs["owner"], ["routines:write"])
    created = client.post(path, json=body, headers=bearer(writer["token"]))
    assert created.status_code == 201, created.text
    [(actor, metadata)] = _audit(superuser, org, action)
    assert actor == uid(client, subs["owner"])
    assert metadata["via"] == "api_token"
    assert (metadata["token_id"], metadata["token"]) == (writer["id"], writer["prefix"])


def test_a_key_updates_only_its_own_organizations_incidents(
    client: TestClient, superuser: Engine
) -> None:
    other, other_subs = org_with(client, superuser)
    theirs = client.post(
        "/api/v1/incidents",
        json=WRITES["/api/v1/incidents"][0],
        headers=bearer(make_key(client, other, other_subs["owner"], ["routines:write"])["token"]),
    ).json()["id"]
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["routines:write"])
    note = {"kind": "note", "note": "Restaurado el servicio."}
    refused = client.post(
        f"/api/v1/incidents/{theirs}/updates", json=note, headers=bearer(key["token"])
    )
    assert refused.status_code == 404
    mine = client.post(
        "/api/v1/incidents", json=WRITES["/api/v1/incidents"][0], headers=bearer(key["token"])
    ).json()["id"]
    added = client.post(
        f"/api/v1/incidents/{mine}/updates", json=note, headers=bearer(key["token"])
    )
    assert added.status_code == 201, added.text
    assert [(a, m["via"]) for a, m in _audit(superuser, org, "incident.note")] == [
        (uid(client, subs["owner"]), "api_token")
    ]


def test_a_training_campaign_started_by_a_key_returns_its_link_once(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["routines:write"])
    created = client.post(
        "/api/v1/training-campaigns",
        json=WRITES["/api/v1/training-campaigns"][0],
        headers=bearer(key["token"]),
    ).json()
    assert "/training#token=" in created["link"]
    with superuser.connect() as conn:
        usage = conn.execute(
            text("SELECT route, scope FROM api_token_usage WHERE token_id = :t"), {"t": key["id"]}
        ).one()
    assert tuple(usage) == ("/api/v1/training-campaigns", "routines:write")
