"""Global search over requirements (console-shell spec), on real PostgreSQL."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from .conftest import auth
from .test_members import org_with
from .test_overview import overview_catalog as overview_catalog
from .test_requirement_register import pack as pack


def _search(client: TestClient, org: str, sub: str, q: str) -> tuple[int, list[dict[str, str]]]:
    response = client.get(f"/api/v1/orgs/{org}/search", params={"q": q}, headers=auth(sub))
    return response.status_code, response.json()


def test_search_matches_code_and_title_without_case_or_accents(
    client: TestClient, superuser: Engine, pack: str
) -> None:
    org, subs = org_with(client, superuser)
    status, results = _search(client, org, subs["owner"], "M.CAT")
    assert status == 200
    assert [r["code"] for r in results] == ["m.cat"]
    assert results[0]["framework_key"] == pack and results[0]["framework_name"]
    status, results = _search(client, org, subs["owner"], "medida sintetica")  # no accent typed
    assert status == 200 and {r["code"] for r in results} == {"m.cat", "m.dim", "m.none"}


@pytest.mark.parametrize("q", ["x", "y" * 101])
def test_search_needs_a_sensible_query(client: TestClient, superuser: Engine, q: str) -> None:
    org, subs = org_with(client, superuser)
    assert _search(client, org, subs["owner"], q)[0] == 422


def test_outsiders_cannot_search(client: TestClient, superuser: Engine) -> None:
    org, _ = org_with(client, superuser)
    _, other = org_with(client, superuser)
    assert _search(client, org, other["owner"], "medida")[0] == 404
