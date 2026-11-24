"""Committed seed rows for the operator API's HTTP tests, written as the superuser.

Every organization gets a unique name, so a test scopes the list with `q=` and never sees
another test's rows. Member emails, connection display names and tenant ids are distinctive
strings, so a response-shape test can search the raw body for them.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Engine, text

NOW = datetime.now(UTC)
SECRETS = (
    "person-secret@customer.test",
    "Display-Secret",
    "7e5a5e00-0000-4000-8000",
)  # a tenant GUID prefix


@dataclass
class Org:
    id: uuid.UUID
    name: str
    owner: uuid.UUID
    users: list[uuid.UUID] = field(default_factory=list)


def run(engine: Engine, statement: str, **params: Any) -> Any:
    with engine.begin() as conn:
        return conn.execute(text(statement), params)


def org(engine: Engine, prefix: str, **columns: Any) -> Org:
    """An organization with an owner whose email is one of SECRETS."""
    org_id, owner = uuid.uuid4(), uuid.uuid4()
    name = f"{prefix} {org_id.hex[:8]}"
    values = {"suspended_at": None, "suspension_reason": None, "closure_requested_at": None}
    values |= columns
    run(
        engine,
        "INSERT INTO organizations (id, name, suspended_at, suspension_reason,"
        " closure_requested_at, trial_ends_at) VALUES (:id, :n, :suspended_at,"
        " :suspension_reason, :closure_requested_at, coalesce(:trial, now() + interval '14 days'))",
        id=org_id,
        n=name,
        trial=values.pop("trial_ends_at", None),
        **values,
    )
    created = Org(org_id, name, owner)
    add_user(engine, created, "owner", email=f"{owner.hex[:6]}-{SECRETS[0]}", user_id=owner)
    return created


def add_user(
    engine: Engine, o: Org, role: str, *, email: str | None = None, user_id: uuid.UUID | None = None
) -> uuid.UUID:
    uid = user_id or uuid.uuid4()
    run(
        engine,
        "INSERT INTO users (id, cognito_sub, email, email_verified) VALUES (:u, :s, :e, true)",
        u=uid,
        s=f"sub-{uid}",
        e=email or f"{uid.hex[:8]}@customer.test",
    )
    run(
        engine,
        "INSERT INTO memberships (organization_id, user_id, role) VALUES (:o, :u, :r)",
        o=o.id,
        u=uid,
        r=role,
    )
    o.users.append(uid)
    return uid


def connection(engine: Engine, o: Org, status: str, provider: str = "m365") -> None:
    run(
        engine,
        "INSERT INTO connections (id, organization_id, provider, status, display_name,"
        " external_tenant_id, created_by) VALUES (gen_random_uuid(), :o, :p, :s, :d, :t, :u)",
        o=o.id,
        p=provider,
        s=status,
        d=f"{SECRETS[1]} {uuid.uuid4().hex[:4]}",
        t=f"{SECRETS[2]}-{uuid.uuid4().hex[:12]}",
        u=o.owner,
    )


def scan(engine: Engine, o: Org, status: str) -> None:
    run(
        engine,
        "INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,"
        " engine_version, queued_at, finished_at) VALUES (gen_random_uuid(), :o,"
        " gen_random_uuid(), 'm365', 'schedule', :s, 'prowler', '5.52.0', :q, :q)",
        o=o.id,
        s=status,
        q=NOW - timedelta(days=1),
    )


def subscription(engine: Engine, o: Org, plan: str, addons: tuple[str, ...] = ()) -> None:
    run(
        engine,
        "INSERT INTO subscriptions (organization_id, plan, addons) VALUES (:o, :p, :a)",
        o=o.id,
        p=plan,
        a=list(addons),
    )


def billing(engine: Engine, o: Org, *, complete: bool = True) -> None:
    run(
        engine,
        "INSERT INTO billing_profiles (organization_id, legal_name, tax_id, address_line1,"
        " postal_code, city, region, country, contact_email) VALUES (:o, :n, 'B12345678',"
        " 'Calle Mayor 1', '28001', 'Madrid', 'Madrid', 'ES', :e)",
        o=o.id,
        n=f"{o.name} S.L.",
        e="facturas@customer.test" if complete else None,
    )
