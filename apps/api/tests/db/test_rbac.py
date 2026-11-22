"""Roles and access (rbac spec), on real PostgreSQL with RLS: the external auditor reads until an
end date and never writes; a contributor assesses only the measures assigned to them."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from .conftest import auth, new_sub
from .test_invitations import accept, token_of
from .test_members import org_with, uid
from .test_overview import overview_catalog as overview_catalog
from .test_requirement_register import SCOPE, assessment, base
from .test_requirement_register import pack as pack


def _add(
    superuser: Engine, client: TestClient, org: str, role: str, expires: datetime | None
) -> str:
    sub = new_sub()
    user = uid(client, sub)
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO memberships (organization_id, user_id, role, access_expires_at)"
                " VALUES (:o, :u, :r, :e)"
            ),
            {"o": org, "u": user, "r": role, "e": expires},
        )
    return sub


def _future(days: int = 30) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


# --- the external auditor ------------------------------------------------------------------


def test_an_auditor_reads_the_workspace_and_exports(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser)
    client.post(
        base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=auth(subs["owner"])
    )
    auditor = _add(superuser, client, org, "auditor", _future())
    headers = auth(auditor)
    assert client.get(f"/api/v1/orgs/{org}/overview", headers=headers).status_code == 200
    assert client.get(base(org, pack) + "/register", headers=headers).status_code == 200
    assert client.get(base(org, pack) + "/applicability.csv", headers=headers).status_code == 200


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("POST", "/scope", {"axis_values": SCOPE}),
        ("POST", "/register/m.cat", None),
        (
            "POST",
            "/assessment-reviews",
            {
                "reviewer_name": "a",
                "reviewer_role": "b",
                "reviewed_on": "2026-11-21",
                "conclusions": "c",
            },
        ),
        ("POST", "/register/m.cat/assignment", {"owner_user_id": None}),
    ],
)
def test_an_auditor_never_writes(
    client: TestClient, superuser: Engine, pack: str, method: str, suffix: str, body: object
) -> None:
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", _future())
    payload = assessment() if body is None else body
    response = client.request(method, base(org, pack) + suffix, json=payload, headers=auth(auditor))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "identity.forbidden"


def test_an_auditor_cannot_write_through_other_modules_either(
    client: TestClient, superuser: Engine
) -> None:
    """The refusal sits in require_member, so an endpoint that forgets a role check stays safe."""
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", _future())
    response = client.post(
        f"/api/v1/orgs/{org}/controls/ctl.any/evidence",
        json={"submission_id": str(uuid.uuid4()), "title": "t", "statement": "s"},
        headers=auth(auditor),
    )
    assert response.status_code == 403


@pytest.mark.parametrize("path", ["members", "invitations", "activity"])
def test_an_auditor_does_not_see_people_or_activity(
    client: TestClient, superuser: Engine, path: str
) -> None:
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", _future())
    assert client.get(f"/api/v1/orgs/{org}/{path}", headers=auth(auditor)).status_code == 403


def test_expired_access_is_refused_even_for_reads(client: TestClient, superuser: Engine) -> None:
    org, _ = org_with(client, superuser)
    auditor = _add(superuser, client, org, "auditor", datetime.now(UTC) - timedelta(minutes=1))
    response = client.get(f"/api/v1/orgs/{org}/overview", headers=auth(auditor))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "identity.access_expired"


def test_the_database_refuses_an_auditor_without_an_end_date(
    client: TestClient, superuser: Engine
) -> None:
    org, _ = org_with(client, superuser)
    with pytest.raises(IntegrityError):
        _add(superuser, client, org, "auditor", None)


# --- adding an auditor ---------------------------------------------------------------------


def _invite(client: TestClient, org: str, by: str, **body: object) -> tuple[int, dict[str, object]]:
    response = client.post(
        f"/api/v1/orgs/{org}/invitations",
        json={"email": f"{new_sub()}@example.com", **body},
        headers=auth(by),
    )
    return response.status_code, response.json()


def test_an_auditor_invitation_needs_an_end_date_within_a_year(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    owner = subs["owner"]
    today = date.today()
    assert _invite(client, org, owner, role="auditor")[0] == 422
    too_far = (today + timedelta(days=366)).isoformat()
    assert _invite(client, org, owner, role="auditor", access_expires_on=too_far)[0] == 422
    past = today.isoformat()
    assert _invite(client, org, owner, role="auditor", access_expires_on=past)[0] == 422
    member_with_date = (today + timedelta(days=30)).isoformat()
    assert _invite(client, org, owner, role="member", access_expires_on=member_with_date)[0] == 422


def test_accepting_an_auditor_invitation_carries_the_end_date(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    guest = new_sub()
    end = (date.today() + timedelta(days=30)).isoformat()
    response = client.post(
        f"/api/v1/orgs/{org}/invitations",
        json={"email": f"{guest}@example.com", "role": "auditor", "access_expires_on": end},
        headers=auth(subs["owner"]),
    )
    assert response.status_code == 201, response.text
    assert accept(client, guest, token_of(response.json()["accept_link"])) == (200, "auditor")
    membership = next(
        m
        for m in client.get("/api/v1/me", headers=auth(guest)).json()["memberships"]
        if m["organization_id"] == org
    )
    assert membership["role"] == "auditor"
    assert membership["access_expires_on"] == end


def test_changing_to_and_from_auditor_sets_and_clears_the_end_date(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    ana = uid(client, subs["ana"])
    url = f"/api/v1/orgs/{org}/members/{ana}"
    owner = auth(subs["owner"])
    assert client.patch(url, json={"role": "auditor"}, headers=owner).status_code == 422
    end = (date.today() + timedelta(days=10)).isoformat()
    changed = client.patch(url, json={"role": "auditor", "access_expires_on": end}, headers=owner)
    assert changed.status_code == 200, changed.text
    assert changed.json()["access_expires_on"] == end
    back = client.patch(url, json={"role": "member"}, headers=owner)
    assert back.status_code == 200 and back.json()["access_expires_on"] is None


# --- the contributor -----------------------------------------------------------------------


def test_a_contributor_assesses_only_their_own_measures(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    owner = auth(subs["owner"])
    client.post(base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=owner)
    ana = uid(client, subs["ana"])
    client.post(
        base(org, pack) + "/register/m.cat/assignment", json={"owner_user_id": ana}, headers=owner
    )
    mine = client.post(
        base(org, pack) + "/register/m.cat", json=assessment(), headers=auth(subs["ana"])
    )
    assert mine.status_code == 201, mine.text
    other = client.post(
        base(org, pack) + "/register/m.dim", json=assessment(), headers=auth(subs["ana"])
    )
    assert other.status_code == 403
    assert other.json()["detail"]["code"] == "compliance.not_owner"
    # Scope and assignment stay with admins.
    assert (
        client.post(
            base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=auth(subs["ana"])
        ).status_code
        == 403
    )


def test_my_work_lists_only_my_measures_with_their_state(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser, ana="member", bea="member")
    owner = auth(subs["owner"])
    client.post(base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=owner)
    ana, bea = uid(client, subs["ana"]), uid(client, subs["bea"])
    for code, person, due in (
        ("m.cat", ana, "2026-12-01"),
        ("m.dim", ana, None),
        ("m.none", bea, None),
    ):
        client.post(
            base(org, pack) + f"/register/{code}/assignment",
            json={"owner_user_id": person, "due_on": due},
            headers=owner,
        )
    client.post(base(org, pack) + "/register/m.cat", json=assessment(), headers=auth(subs["ana"]))
    items = client.get(f"/api/v1/orgs/{org}/my-work", headers=auth(subs["ana"])).json()
    assert [(i["code"], i["due_on"], i["implementation"]) for i in items] == [
        ("m.cat", "2026-12-01", "implemented"),
        ("m.dim", None, None),
    ]
    assert items[0]["framework_key"] == pack
    auditor = _add(superuser, client, org, "auditor", _future())
    assert client.get(f"/api/v1/orgs/{org}/my-work", headers=auth(auditor)).status_code == 403
