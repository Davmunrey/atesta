"""Readiness counts for the dashboard cockpit (readiness-cockpit spec), on real PostgreSQL."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from .conftest import auth
from .test_members import org_with, uid
from .test_overview import overview_catalog as overview_catalog
from .test_rbac import _add, _future
from .test_requirement_register import SCOPE, assessment, base
from .test_requirement_register import pack as pack


def _entry(client: TestClient, org: str, sub: str, key: str) -> dict[str, object]:
    response = client.get(f"/api/v1/orgs/{org}/readiness", headers=auth(sub))
    assert response.status_code == 200, response.text
    return next(e for e in response.json() if e["key"] == key)


def test_readiness_counts_the_latest_self_assessment(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser, ana="member")
    owner = auth(subs["owner"])
    empty = _entry(client, org, subs["owner"], pack)
    assert empty["total"] == 3 and empty["assessed"] == 0
    assert empty["has_axes"] is True and empty["scope_defined"] is False
    assert empty["review_on"] is None and empty["last_assessed_at"] is None

    client.post(base(org, pack) + "/scope", json={"axis_values": SCOPE}, headers=owner)
    client.post(
        base(org, pack) + "/register/m.cat",
        json=assessment(implementation="partially_implemented"),
        headers=owner,
    )
    client.post(
        base(org, pack) + "/register/m.cat", json=assessment(), headers=owner
    )  # latest wins
    client.post(
        base(org, pack) + "/register/m.dim",
        json=assessment(applicability="not_applicable", justification="Fuera del sistema."),
        headers=owner,
    )
    ana = uid(client, subs["ana"])
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    client.post(
        base(org, pack) + "/register/m.none/assignment",
        json={"owner_user_id": ana, "due_on": yesterday},
        headers=owner,
    )
    client.post(
        base(org, pack) + "/register/m.cat/assignment",
        json={"owner_user_id": ana, "due_on": yesterday},
        headers=owner,
    )

    entry = _entry(client, org, subs["ana"], pack)
    assert (
        entry["assessed"],
        entry["implemented"],
        entry["partial"],
        entry["not_implemented"],
        entry["not_applicable"],
    ) == (2, 1, 0, 0, 1)
    assert entry["scope_defined"] is True
    assert entry["overdue"] == 1  # m.cat is implemented, so only m.none is overdue
    assert entry["unowned_open"] == 0
    assert entry["open_by_owner"] == {ana: 1}
    assert entry["last_assessed_at"] is not None


def test_another_organization_never_counts_and_auditors_read_counts(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser)
    other, other_subs = org_with(client, superuser)
    client.post(
        base(other, pack) + "/register/m.cat", json=assessment(), headers=auth(other_subs["owner"])
    )
    entry = _entry(client, org, subs["owner"], pack)
    assert entry["assessed"] == 0 and entry["unowned_open"] == 3
    auditor = _add(superuser, client, org, "auditor", _future())
    assert _entry(client, org, auditor, pack)["total"] == 3


def test_frameworks_without_requirements_are_absent(
    client: TestClient, superuser: Engine, overview_catalog: dict[str, str]
) -> None:
    org, subs = org_with(client, superuser)
    response = client.get(f"/api/v1/orgs/{org}/readiness", headers=auth(subs["owner"]))
    assert response.status_code == 200
    assert all(e["total"] > 0 for e in response.json())
