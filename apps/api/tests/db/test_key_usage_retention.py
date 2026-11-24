"""Retention of the API key usage log (api-keys-v2 spec, issue 353), on real PostgreSQL.

Owner decision, 2026-11-24: the worker deletes, the database sets the limit. The runtime role
may delete a usage row only once it is 90 days old, and only in its own organization.
"""

import uuid
from datetime import UTC, datetime

import pytest
from atesta_api.modules.identity.api import (
    USAGE_RETENTION,
    ContextReason,
    enter_org_context,
    expire_key_usage,
)
from atesta_api.platform.tables import RETENTION_DAYS
from atesta_worker import context, jobs
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from .conftest import auth
from .test_api_keys_v2 import KEY, bearer, make_key
from .test_members import org_with


def aged(superuser: Engine, token_id: str, days: list[int]) -> list[uuid.UUID]:
    """One usage row per entry of `days`, that many days and one hour old."""
    ids = [uuid.uuid4() for _ in days]
    with superuser.begin() as conn:
        for row_id, age in zip(ids, days, strict=True):
            conn.execute(
                text(
                    "INSERT INTO api_token_usage (id, organization_id, token_id, at, method, route)"
                    " SELECT :id, organization_id, id,"
                    " now() - make_interval(days => :d, hours => 1), 'GET', '/api/v1/key'"
                    " FROM api_tokens WHERE id = :t"
                ),
                {"id": row_id, "d": age, "t": token_id},
            )
    return ids


def left(superuser: Engine, ids: list[uuid.UUID]) -> list[bool]:
    with superuser.connect() as conn:
        found = set(
            conn.scalars(text("SELECT id FROM api_token_usage WHERE id = ANY(:ids)"), {"ids": ids})
        )
    return [row_id in found for row_id in ids]


def in_org(factory: sessionmaker[Session], org: str) -> Session:
    session = factory()
    session.begin()
    enter_org_context(session, uuid.UUID(org), ContextReason.JOB)
    return session


def test_the_period_is_ninety_days_everywhere(superuser: Engine) -> None:
    assert USAGE_RETENTION.days == RETENTION_DAYS["api_token_usage"] == 90
    with superuser.connect() as conn:
        policy = conn.execute(
            text(
                "SELECT cmd, permissive, array_to_string(roles, ','), qual FROM pg_policies"
                " WHERE tablename = 'api_token_usage' AND policyname = 'retention'"
            )
        ).one()
    assert tuple(policy[:3]) == ("DELETE", "RESTRICTIVE", "public")
    assert "'90 days'::interval" in policy[3]


def test_the_database_refuses_to_delete_a_young_row_whatever_the_code_asks(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["compliance:read"])
    other, other_subs = org_with(client, superuser)
    other_key = make_key(client, other, other_subs["owner"], ["compliance:read"])
    mine = aged(superuser, key["id"], [0, 89, 90, 400])
    theirs = aged(superuser, other_key["id"], [400])
    with in_org(db_commit, org) as session:
        session.execute(text("DELETE FROM api_token_usage"))  # no WHERE at all
        session.commit()
    assert left(superuser, mine) == [True, True, False, False]
    assert left(superuser, theirs) == [True]


def test_a_usage_row_can_never_be_changed(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["compliance:read"])
    aged(superuser, key["id"], [400])
    with in_org(db_commit, org) as session, pytest.raises(ProgrammingError, match="permission"):
        session.execute(text("UPDATE api_token_usage SET at = now() - interval '5 years'"))


def test_expiry_deletes_only_this_organizations_old_rows(
    client: TestClient, superuser: Engine, db_commit: sessionmaker[Session]
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["compliance:read"])
    other, other_subs = org_with(client, superuser)
    other_key = make_key(client, other, other_subs["owner"], ["compliance:read"])
    mine = aged(superuser, key["id"], [1, 89, 90, 91])
    theirs = aged(superuser, other_key["id"], [91])
    now = datetime.now(UTC)
    with in_org(db_commit, org) as session:
        assert expire_key_usage(session, uuid.UUID(org), now=now) == 2
        assert expire_key_usage(session, uuid.UUID(org), now=now) == 0
        # Asking for another organization's rows deletes nothing: tenant_isolation still applies.
        assert expire_key_usage(session, uuid.UUID(other), now=now) == 0
        session.commit()
    assert left(superuser, mine) == [True, True, False, False]
    assert left(superuser, theirs) == [True]


def test_the_daily_job_expires_the_log_and_the_limit_and_the_view_still_answer(
    client: TestClient, superuser: Engine, app_engine: Engine
) -> None:
    org, subs = org_with(client, superuser)
    key = make_key(client, org, subs["owner"], ["compliance:read"], limit=2)
    assert client.get(KEY, headers=bearer(key["token"])).status_code == 200
    old = aged(superuser, key["id"], [91, 200])
    context.configure(app_engine)
    jobs.notify_daily(org)
    jobs.notify_daily(org)  # a second run finds nothing left
    assert left(superuser, old) == [False, False]
    usage = client.get(
        f"/api/v1/orgs/{org}/api-tokens/{key['id']}/usage", headers=auth(subs["owner"])
    ).json()
    assert usage["last_24h"] == 1
    assert [row["route"] for row in usage["recent"]] == ["/api/v1/key"]
    assert client.get(KEY, headers=bearer(key["token"])).status_code == 200
    assert client.get(KEY, headers=bearer(key["token"])).status_code == 429  # limit of 2 a minute
