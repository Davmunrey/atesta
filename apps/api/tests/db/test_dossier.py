"""Auditor dossier (auditor-dossier spec), on real PostgreSQL with RLS."""

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from atesta_api.modules.compliance.register import NOT_A_CERTIFICATION
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_members import events, org_with
from .test_overview import overview_catalog as overview_catalog
from .test_rbac import _add, _future
from .test_requirement_register import assessment, base
from .test_requirement_register import pack as pack


@pytest.fixture
def mapped(superuser: Engine, pack: str) -> Iterator[tuple[str, str]]:
    control = f"ctl.dossier_{uuid.uuid4().hex[:10]}"
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO controls (key, title_es, title_en, description_es, description_en,"
                " manual) VALUES (:k, 'Política', 'Policy', 'Guía', 'Guide', true)"
            ),
            {"k": control},
        )
        conn.execute(
            text(
                "INSERT INTO mappings (framework_key, requirement_code, control_key, rationale,"
                " source) VALUES (:f, 'm.cat', :k, 'candidate', 'synthetic')"
            ),
            {"f": pack, "k": control},
        )
    yield pack, control
    with superuser.begin() as conn:
        conn.execute(text("DELETE FROM mappings WHERE control_key = :k"), {"k": control})
        conn.execute(text("DELETE FROM evidence_controls WHERE control_key = :k"), {"k": control})
        conn.execute(text("DELETE FROM controls WHERE key = :k"), {"k": control})


def _statement(client: TestClient, org: str, control: str, sub: str, title: str) -> None:
    response = client.post(
        f"/api/v1/orgs/{org}/controls/{control}/evidence",
        json={
            "submission_id": str(uuid.uuid4()),
            "title": title,
            "statement": f"{title}: approved by the security committee.",
            "reference_url": "https://example.test/policy",
        },
        headers=auth(sub),
    )
    assert response.status_code == 201, response.text


def test_the_dossier_gathers_the_pieces_for_the_auditor(
    client: TestClient, superuser: Engine, mapped: tuple[str, str]
) -> None:
    framework, control = mapped
    org, subs = org_with(client, superuser)
    other, other_subs = org_with(client, superuser)
    recorded = client.post(
        base(org, framework) + "/register/m.cat", json=assessment(), headers=auth(subs["owner"])
    )
    assert recorded.status_code == 201, recorded.text
    _statement(client, org, control, subs["owner"], "Security policy")
    _statement(client, other, control, other_subs["owner"], "Someone else's policy")
    policy = client.post(
        f"/api/v1/orgs/{org}/policies",
        json={
            "title": "Política de seguridad",
            "location_url": "https://example.test/p",
            "review_months": 12,
        },
        headers=auth(subs["owner"]),
    ).json()
    client.post(
        f"/api/v1/orgs/{org}/policies/{policy['id']}/approvals",
        json={"version": "1.0", "approver_name": "Comité", "approved_on": date.today().isoformat()},
        headers=auth(subs["owner"]),
    )
    auditor = _add(superuser, client, org, "auditor", _future())
    response = client.get(base(org, framework) + "/dossier", headers=auth(auditor))
    assert response.status_code == 200, response.text
    dossier = response.json()
    assert dossier["statement"] == NOT_A_CERTIFICATION
    counts = dossier["summary"]["counts"]
    assert (counts["total"], counts["assessed"], counts["implemented"]) == (3, 1, 1)
    assert len(dossier["applicability"]) == 3
    by_code = {r["code"]: r for r in dossier["requirements"]}
    mapped_controls = by_code["m.cat"]["controls"]
    assert [c["key"] for c in mapped_controls] == [control]
    assert [e["title"] for e in mapped_controls[0]["evidence"]] == ["Security policy"]
    assert by_code["m.cat"]["implementation"] == "implemented"
    assert [p["title"] for p in dossier["routines"]["policies"]] == ["Política de seguridad"]
    assert dossier["summary"]["routines"]["policies_unapproved"] == 0
    assert events(superuser, org, "framework.dossier_viewed") == 1


def test_an_unknown_framework_has_no_dossier(client: TestClient, superuser: Engine) -> None:
    org, subs = org_with(client, superuser)
    response = client.get(base(org, "no_such_pack") + "/dossier", headers=auth(subs["owner"]))
    assert response.status_code == 404
