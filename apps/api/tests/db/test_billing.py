"""Billing entitlements are enforced at the API boundary (billing-entitlements spec), on real
PostgreSQL with RLS. Plans are set as the operator does: a row written by the owner role."""

import pytest
from atesta_api.modules.billing import api as billing
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError

from .conftest import auth
from .test_dossier import mapped as mapped
from .test_members import org_with
from .test_overview import overview_catalog as overview_catalog
from .test_requirement_register import base
from .test_requirement_register import pack as pack

LIMIT = "billing.plan_limit"


def _plan(superuser: Engine, org: str, plan: str, addons: tuple[str, ...] = ()) -> None:
    with superuser.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO subscriptions (organization_id, plan, addons, note)"
                " VALUES (:o, :p, :a, 'set in a test')"
            ),
            {"o": org, "p": plan, "a": list(addons)},
        )


@pytest.fixture
def grants(monkeypatch: pytest.MonkeyPatch, pack: str) -> str:
    """Starter and pro get the synthetic pack, as plans.yaml grants them the first pack."""
    raw = {"plans": {"starter": {pack: ["low"]}, "pro": {pack: "all"}, "business": "all"}}
    parsed = billing.parse_grants(raw, frozenset({pack}))
    monkeypatch.setattr(billing, "_grants", lambda: parsed)
    return pack


def _connect(client: TestClient, org: str, sub: str) -> tuple[int, dict[str, object]]:
    body = {"provider": "m365", "display_name": "Contoso M365"}
    response = client.post(f"/api/v1/orgs/{org}/connections", json=body, headers=auth(sub))
    return response.status_code, response.json()


def _refused(response_json: dict[str, object], limit: str) -> bool:
    return response_json.get("detail") == {"code": LIMIT, "limit": limit}


def test_an_organization_without_a_plan_keeps_everything(
    client: TestClient, superuser: Engine, mapped: tuple[str, str]
) -> None:
    """Every pilot organization has no subscription row: the default plan, business, applies."""
    framework, _ = mapped
    org, subs = org_with(client, superuser)
    owner = auth(subs["owner"])
    assert [_connect(client, org, subs["owner"])[0] for _ in range(4)] == [201] * 4
    assert client.get(base(org, framework), headers=owner).status_code == 200
    assert client.get(base(org, framework) + "/dossier", headers=owner).status_code == 200
    assert billing.DEFAULT_PLAN is billing.Plan.BUSINESS


def test_starter_holds_one_connection_and_a_disconnected_one_frees_the_slot(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    _plan(superuser, org, "starter")
    status, first = _connect(client, org, subs["owner"])
    assert status == 201
    status, refused = _connect(client, org, subs["owner"])
    assert status == 403 and _refused(refused, "connectors")
    url = f"/api/v1/orgs/{org}/connections/{first['id']}"
    assert client.delete(url, headers=auth(subs["owner"])).status_code == 200
    assert _connect(client, org, subs["owner"])[0] == 201


def test_a_downgrade_keeps_the_connections_that_exist(
    client: TestClient, superuser: Engine
) -> None:
    org, subs = org_with(client, superuser)
    made = [_connect(client, org, subs["owner"])[1] for _ in range(2)]
    _plan(superuser, org, "starter")
    listed = client.get(f"/api/v1/orgs/{org}/connections", headers=auth(subs["owner"])).json()
    assert {c["id"] for c in listed} == {c["id"] for c in made}
    assert all(c["status"] != "disconnected" for c in listed)
    status, refused = _connect(client, org, subs["owner"])
    assert status == 403 and _refused(refused, "connectors")


def test_the_dossier_needs_evidence_export(
    client: TestClient, superuser: Engine, mapped: tuple[str, str], grants: str
) -> None:
    starter, starter_subs = org_with(client, superuser)
    pro, pro_subs = org_with(client, superuser)
    bought, bought_subs = org_with(client, superuser)
    _plan(superuser, starter, "starter")
    _plan(superuser, pro, "pro")
    _plan(superuser, bought, "starter", ("evidence_export",))
    refused = client.get(base(starter, grants) + "/dossier", headers=auth(starter_subs["owner"]))
    assert refused.status_code == 403 and _refused(refused.json(), "evidence_export")
    # The framework itself stays open to starter: only the export is beyond the plan.
    assert client.get(base(starter, grants), headers=auth(starter_subs["owner"])).status_code == 200
    for org, subs in ((pro, pro_subs), (bought, bought_subs)):
        response = client.get(base(org, grants) + "/dossier", headers=auth(subs["owner"]))
        assert response.status_code == 200, response.text


def test_a_framework_beyond_the_plan_is_refused_on_read_and_write(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    """The repository grants starter only the ENS pack; the synthetic pack is beyond it."""
    org, subs = org_with(client, superuser, ana="member")
    _plan(superuser, org, "starter")
    for path in ("", "/register", "/scope", "/applicability", "/dossier"):
        response = client.get(base(org, pack) + path, headers=auth(subs["ana"]))
        assert response.status_code == 403 and _refused(response.json(), "framework"), path
    scope = {"axis_values": {"categoría": "MEDIA"}}
    written = client.post(base(org, pack) + "/scope", json=scope, headers=auth(subs["owner"]))
    assert written.status_code == 403 and _refused(written.json(), "framework")


def test_unknown_frameworks_and_strangers_still_get_404(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser)
    _, stranger_subs = org_with(client, superuser)
    _plan(superuser, org, "starter")
    unknown = client.get(base(org, "no_such_pack"), headers=auth(subs["owner"]))
    assert unknown.status_code == 404
    stranger = client.get(base(org, pack), headers=auth(stranger_subs["owner"]))
    assert stranger.status_code == 404


def test_another_organizations_plan_never_applies(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    limited, _ = org_with(client, superuser)
    open_org, subs = org_with(client, superuser)
    _plan(superuser, limited, "starter")
    assert client.get(base(open_org, pack), headers=auth(subs["owner"])).status_code == 200
    assert [_connect(client, open_org, subs["owner"])[0] for _ in range(2)] == [201, 201]


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO subscriptions (organization_id, plan)"
        " SELECT id, 'business' FROM organizations LIMIT 1",
        "UPDATE subscriptions SET plan = 'business'",
        "DELETE FROM subscriptions",
    ],
)
def test_the_app_never_writes_a_plan(app_engine: Engine, statement: str) -> None:
    with app_engine.connect() as conn, pytest.raises(ProgrammingError, match="permission denied"):
        conn.execute(text(statement))


def test_the_database_refuses_an_unknown_plan(client: TestClient, superuser: Engine) -> None:
    org, _ = org_with(client, superuser)
    with pytest.raises(Exception, match="ck_subscriptions_plan"):
        _plan(superuser, org, "enterprise")
