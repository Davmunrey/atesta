"""Read routes for API keys (api-keys-v2 spec, #341), on real PostgreSQL with RLS.

The tenancy sweep calls every GET token route with a key of one organization while another
organization holds data marked SECRET, and checks that nothing of it comes back.
"""

import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_api_keys_v2 import READ, WRITE, bearer, make_key
from .test_members import org_with
from .test_overview import overview_catalog as overview_catalog
from .test_route_sweep import TOKEN_ROUTES

SECRET = "ORG-B-SECRET"
OFFICIAL = "Texto oficial sintético de la medida."
SCOPE_OF = {
    "/api/v1/frameworks": "compliance:read",
    "/api/v1/frameworks/{framework_key}/measures": "compliance:read",
    "/api/v1/frameworks/{framework_key}/measures/{code}": "compliance:read",
    "/api/v1/gaps": "compliance:read",
    "/api/v1/due": "compliance:read",
    "/api/v1/incidents": "incidents:read",
    "/api/v1/incidents/{incident_id}": "incidents:read",
}


@pytest.fixture
def agent_pack(superuser: Engine, overview_catalog: dict[str, str]) -> Iterator[str]:
    """One measure with its official text, guide-referenced evidence and a mapped control."""
    key = overview_catalog["active"]
    control = f"ctl.agent_{uuid.uuid4().hex[:10]}"
    attributes = {
        "official_text_es": OFFICIAL,
        "section": "3.1",
        "source_sha256": hashlib.sha256(OFFICIAL.encode()).hexdigest(),
        "expected_evidence": {
            "reviewed_by": None,
            "items": [
                {
                    "es": "Política aprobada.",
                    "en": "Approved policy.",
                    "ref": {
                        "guide": "CCN-STIC 808",
                        "edition": "2026-04",
                        "section": "6",
                        "page": 18,
                    },
                }
            ],
        },
    }
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO requirements (framework_key, code, title_es, title_en, source,"
                " attributes) VALUES (:k, 'm.one', 'Medida uno', NULL,"
                " 'https://www.boe.es/example#m1', CAST(:a AS jsonb)),"
                " (:k, 'm.two', 'Medida dos', NULL, 'https://www.boe.es/example#m2', '{}')"
            ),
            {"k": key, "a": json.dumps(attributes)},
        )
        conn.execute(
            text(
                "INSERT INTO controls (key, title_es, title_en, description_es, description_en,"
                " manual) VALUES (:c, 'C', 'C', 'D', 'D', true)"
            ),
            {"c": control},
        )
        conn.execute(
            text(
                "INSERT INTO mappings (framework_key, requirement_code, control_key, rationale,"
                " source) VALUES (:k, 'm.one', :c, 'r', 's')"
            ),
            {"k": key, "c": control},
        )
    yield key
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM mappings WHERE framework_key = :k"), {"k": key})
        conn.execute(text("DELETE FROM controls WHERE key = :c"), {"c": control})
        conn.execute(text("DELETE FROM requirements WHERE framework_key = :k"), {"k": key})


def _assess(client: TestClient, org: str, sub: str, pack: str, code: str, notes: str) -> None:
    body = {
        "applicability": "applies",
        "implementation": "partially_implemented",
        "regularly_reviewed": False,
        "notes": notes,
    }
    url = f"/api/v1/orgs/{org}/frameworks/{pack}/register/{code}"
    assert client.post(url, json=body, headers=auth(sub)).status_code == 201


def _incident(client: TestClient, org: str, sub: str, title: str) -> str:
    aware = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    body = {"title": title, "aware_at": aware, "significant": True, "personal_data": False}
    response = client.post(f"/api/v1/orgs/{org}/incidents", json=body, headers=auth(sub))
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _seed_secret_org(client: TestClient, superuser: Engine, pack: str) -> tuple[str, str]:
    org, subs = org_with(client, superuser)
    _assess(client, org, subs["owner"], pack, "m.one", SECRET)
    incident = _incident(client, org, subs["owner"], SECRET)
    policy = {"title": SECRET, "location_url": "https://example.test/p", "review_months": 1}
    client.post(f"/api/v1/orgs/{org}/policies", json=policy, headers=auth(subs["owner"]))
    return org, incident


def _fill(path: str, pack: str, incident: str) -> str:
    values = {"framework_key": pack, "code": "m.one", "incident_id": incident}
    return re.sub(r"\{([a-z_]+)\}", lambda m: values[m.group(1)], path)


def test_every_read_route_is_listed_with_its_scope() -> None:
    gets = {path for method, path in TOKEN_ROUTES if method == "GET"} - {"/api/v1/key"}
    assert gets == set(SCOPE_OF)


@pytest.mark.parametrize("path", sorted(SCOPE_OF))
def test_every_read_route_needs_its_scope(
    client: TestClient, superuser: Engine, agent_pack: str, path: str
) -> None:
    org, subs = org_with(client, superuser)
    incident = _incident(client, org, subs["owner"], "Caída del correo")
    others = [s for s in READ + WRITE if s != SCOPE_OF[path]]
    key = make_key(client, org, subs["owner"], others)
    refused = client.get(_fill(path, agent_pack, incident), headers=bearer(key["token"]))
    assert refused.status_code == 403
    assert refused.json()["detail"]["scope"] == SCOPE_OF[path]
    allowed = make_key(client, org, subs["owner"], [SCOPE_OF[path]])
    response = client.get(_fill(path, agent_pack, incident), headers=bearer(allowed["token"]))
    assert response.status_code == 200, response.text


def test_no_read_route_reaches_another_organization(
    client: TestClient, superuser: Engine, agent_pack: str
) -> None:
    other, other_incident = _seed_secret_org(client, superuser, agent_pack)
    org, subs = org_with(client, superuser)
    _assess(client, org, subs["owner"], agent_pack, "m.one", "Nuestra nota")
    own_incident = _incident(client, org, subs["owner"], "Nuestro incidente")
    key = make_key(client, org, subs["owner"], READ, limit=600)
    seen: dict[str, str] = {}
    for path in sorted(SCOPE_OF):
        response = client.get(_fill(path, agent_pack, own_incident), headers=bearer(key["token"]))
        assert response.status_code == 200, (path, response.text)
        seen[path] = response.text
    assert all(SECRET not in body and other not in body for body in seen.values())
    assert all(other_incident not in body for body in seen.values())
    assert "Nuestro incidente" in seen["/api/v1/incidents"]
    assert "Nuestra nota" in seen["/api/v1/frameworks/{framework_key}/measures"]
    theirs = client.get(f"/api/v1/incidents/{other_incident}", headers=bearer(key["token"]))
    assert theirs.status_code == 404


def test_a_measure_carries_its_official_text_and_citation(
    client: TestClient, superuser: Engine, agent_pack: str
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["compliance:read"])
    url = f"/api/v1/frameworks/{agent_pack}/measures/m.one"
    measure = client.get(url, headers=bearer(key["token"])).json()
    assert measure["official_text_es"] == OFFICIAL
    assert measure["citation"] == {
        "source": "https://www.boe.es/example#m1",
        "section": "3.1",
        "source_sha256": hashlib.sha256(OFFICIAL.encode()).hexdigest(),
        "catalog_version": "v2",
        "framework_version": "current",
    }
    assert measure["expected_evidence"][0]["ref"]["guide"] == "CCN-STIC 808"
    assert len(measure["controls"]) == 1 and measure["controls"][0].startswith("ctl.agent_")
    missing = client.get(url.replace("m.one", "m.nope"), headers=bearer(key["token"]))
    assert missing.status_code == 404


def test_gaps_list_what_is_not_done(client: TestClient, superuser: Engine, agent_pack: str) -> None:
    org, subs = org_with(client, superuser)
    _assess(client, org, subs["owner"], agent_pack, "m.one", "")
    key = make_key(client, org, subs["owner"], ["compliance:read"])
    gaps = client.get("/api/v1/gaps", headers=bearer(key["token"])).json()
    mine = {(g["framework_key"], g["code"]): g["state"] for g in gaps}
    assert mine[(agent_pack, "m.one")] == "partially_implemented"
    assert mine[(agent_pack, "m.two")] == "not_assessed"


def test_the_plan_still_decides(client: TestClient, superuser: Engine, agent_pack: str) -> None:
    org, subs = org_with(client, superuser)
    with superuser.begin() as conn:
        conn.execute(
            text("INSERT INTO subscriptions (organization_id, plan) VALUES (:o, 'starter')"),
            {"o": org},
        )
    key = make_key(client, org, subs["owner"], ["compliance:read"])
    listed = client.get("/api/v1/frameworks", headers=bearer(key["token"])).json()
    assert agent_pack not in {f["key"] for f in listed}
    measures = client.get(f"/api/v1/frameworks/{agent_pack}/measures", headers=bearer(key["token"]))
    assert (measures.status_code, measures.json()["detail"]["code"]) == (403, "billing.plan_limit")
    unknown = client.get("/api/v1/frameworks/nope/measures", headers=bearer(key["token"]))
    assert unknown.status_code == 404
