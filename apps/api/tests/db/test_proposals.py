"""Self-assessment proposals from API keys (mcp-server spec, #339; ADR-005), on real PostgreSQL.

An agent proposes; only a person's confirmation records the assessment, as that person's.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from .conftest import auth
from .test_api_keys_v2 import bearer, make_key
from .test_key_reads import agent_pack as agent_pack
from .test_members import events, org_with, uid
from .test_overview import overview_catalog as overview_catalog
from .test_rbac import _add, _future


def proposal(**changes: object) -> dict[str, object]:
    return {
        "applicability": "applies",
        "implementation": "implemented",
        "regularly_reviewed": True,
        "performed_by": "Responsable de sistemas",
        "notes": "La política está aprobada y publicada en la intranet.",
        "rationale": "El acta del comité de 2026-11-02 aprueba la política.",
        **changes,
    }


def _propose(client: TestClient, token: str, pack: str, code: str = "m.one", **changes: object):  # type: ignore[no-untyped-def]  # a response
    url = f"/api/v1/frameworks/{pack}/measures/{code}/proposals"
    return client.post(url, json=proposal(**changes), headers=bearer(token))


def _register(client: TestClient, org: str, sub: str, pack: str) -> dict:  # type: ignore[type-arg]  # JSON body
    url = f"/api/v1/orgs/{org}/frameworks/{pack}/register"
    response = client.get(url, headers=auth(sub))
    assert response.status_code == 200, response.text
    return {item["code"]: item for item in response.json()["items"]}


def _decide(client: TestClient, org: str, sub: str, pack: str, proposal_id: str, verb: str):  # type: ignore[no-untyped-def]  # a response
    url = f"/api/v1/orgs/{org}/frameworks/{pack}/proposals/{proposal_id}/{verb}"
    return client.post(url, headers=auth(sub))


def _readiness(client: TestClient, org: str, sub: str, pack: str) -> dict:  # type: ignore[type-arg]  # JSON body
    rows = client.get(f"/api/v1/orgs/{org}/readiness", headers=auth(sub)).json()
    return next(r for r in rows if r["key"] == pack)


def test_a_proposal_is_pending_until_a_person_confirms_it(
    client: TestClient, superuser: Engine, agent_pack: str
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["assessment:propose", "compliance:read"])
    before = _readiness(client, org, subs["owner"], agent_pack)
    created = _propose(client, key["token"], agent_pack)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["status"], body["code"]) == ("pending", "m.one")
    # Nothing about the measure changed: no assessment, same counts.
    item = _register(client, org, subs["owner"], agent_pack)["m.one"]
    assert item["assessment"] is None
    assert item["pending_proposal"]["rationale"] == proposal()["rationale"]
    assert item["pending_proposal"]["token_prefix"] == key["prefix"]
    assert _readiness(client, org, subs["owner"], agent_pack) == before
    measures = client.get(
        f"/api/v1/frameworks/{agent_pack}/measures", headers=bearer(key["token"])
    ).json()
    assert next(m for m in measures if m["code"] == "m.one")["pending_proposal_id"] == body["id"]
    # A person confirms: the assessment is theirs.
    confirmed = _decide(client, org, subs["owner"], agent_pack, body["id"], "confirm")
    assert confirmed.status_code == 201, confirmed.text
    item = _register(client, org, subs["owner"], agent_pack)["m.one"]
    assert item["pending_proposal"] is None
    assert item["assessment"]["implementation"] == "implemented"
    assert item["assessment"]["recorded_by"] == uid(client, subs["owner"])
    assert _readiness(client, org, subs["owner"], agent_pack)["implemented"] == 1
    assert events(superuser, org, "assessment_proposal.created") == 1
    assert events(superuser, org, "assessment_proposal.confirmed") == 1
    with superuser.begin() as conn:
        assessed = conn.execute(
            text(
                "SELECT actor_user_id, metadata FROM audit_events"
                " WHERE organization_id = :o AND action = 'requirement.assessed'"
            ),
            {"o": org},
        ).one()
    assert str(assessed.actor_user_id) == uid(client, subs["owner"])
    assert assessed.metadata["from_proposal"] is True
    again = _decide(client, org, subs["owner"], agent_pack, body["id"], "reject")
    assert (again.status_code, again.json()["detail"]["code"]) == (
        409,
        "compliance.proposal_decided",
    )


def test_a_rejected_proposal_changes_nothing(
    client: TestClient, superuser: Engine, agent_pack: str
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["assessment:propose"])
    first = _propose(client, key["token"], agent_pack).json()
    second = _propose(client, key["token"], agent_pack)
    assert (second.status_code, second.json()["detail"]["code"]) == (
        409,
        "compliance.proposal_pending",
    )
    rejected = _decide(client, org, subs["owner"], agent_pack, first["id"], "reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    item = _register(client, org, subs["owner"], agent_pack)["m.one"]
    assert (item["assessment"], item["pending_proposal"]) == (None, None)
    assert events(superuser, org, "assessment_proposal.rejected") == 1
    assert events(superuser, org, "requirement.assessed") == 0
    # Once decided, a new proposal may follow.
    assert _propose(client, key["token"], agent_pack).status_code == 201


def test_only_people_who_may_assess_decide(
    client: TestClient, superuser: Engine, agent_pack: str
) -> None:
    org, subs = org_with(client, superuser, ana="member", eva="member")
    key = make_key(client, org, subs["owner"], ["assessment:propose"])
    pending = _propose(client, key["token"], agent_pack).json()["id"]
    auditor = _add(superuser, client, org, "auditor", _future())
    assert _decide(client, org, auditor, agent_pack, pending, "confirm").status_code == 403
    refused = _decide(client, org, subs["ana"], agent_pack, pending, "confirm")
    assert (refused.status_code, refused.json()["detail"]["code"]) == (403, "compliance.not_owner")
    assignment = {"owner_user_id": uid(client, subs["ana"]), "due_on": None}
    url = f"/api/v1/orgs/{org}/frameworks/{agent_pack}/register/m.one/assignment"
    assert client.post(url, json=assignment, headers=auth(subs["owner"])).status_code == 201
    assert _decide(client, org, subs["eva"], agent_pack, pending, "confirm").status_code == 403
    assert _decide(client, org, subs["ana"], agent_pack, pending, "confirm").status_code == 201
    other, other_subs = org_with(client, superuser)
    assert (
        _decide(client, other, other_subs["owner"], agent_pack, pending, "confirm").status_code
        == 404
    )


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        (
            {"applicability": "not_applicable", "justification": ""},
            "compliance.justification_required",
        ),
        ({"rationale": ""}, "request.invalid"),
        ({"rationale": "r" * 2001}, "request.invalid"),
        (
            {"evidence_statement_ids": ["00000000-0000-4000-8000-000000000001"]},
            "compliance.evidence_not_found",
        ),
    ],
)
def test_a_proposal_is_checked_like_an_assessment(
    client: TestClient, superuser: Engine, agent_pack: str, changes: dict[str, object], code: str
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["assessment:propose"])
    response = _propose(client, key["token"], agent_pack, **changes)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, code)


def test_proposing_needs_its_scope_and_a_known_measure(
    client: TestClient, superuser: Engine, agent_pack: str
) -> None:
    org, subs = org_with(client, superuser)
    reader = make_key(client, org, subs["owner"], ["compliance:read", "evidence:write"])
    refused = _propose(client, reader["token"], agent_pack)
    assert (refused.status_code, refused.json()["detail"]["scope"]) == (403, "assessment:propose")
    key = make_key(client, org, subs["owner"], ["assessment:propose"])
    assert _propose(client, key["token"], agent_pack, code="m.nope").status_code == 404
    assert _propose(client, key["token"], "nope").status_code == 404


def test_proposals_table_grants(superuser: Engine) -> None:
    with superuser.begin() as conn:
        grants = set(
            conn.scalars(
                text(
                    "SELECT privilege_type FROM information_schema.role_table_grants"
                    " WHERE grantee = 'atesta_app' AND table_name = 'assessment_proposals'"
                )
            )
        )
    assert grants == {"SELECT", "INSERT", "UPDATE"}
