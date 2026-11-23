"""Tenant isolation under RLS (tenant-data-layer spec, test plan)."""

import uuid

import pytest
from atesta_api.platform.context import TenantContext
from atesta_api.platform.tenancy import set_tenant_context
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker

from .conftest import ORG_A, ORG_B

SETTINGS = (
    "app.subject",
    "app.user_id",
    "app.organization_id",
    "app.invitation_token_sha256",
    "app.training_token_sha256",
    "app.api_token_sha256",
)


def rls_tables(session: Session) -> list[str]:
    rows = session.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"
        )
    )
    return sorted(r[0] for r in rows)


def count(session: Session, table: str) -> int:
    assert table.isidentifier()
    return int(session.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())  # noqa: S608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text - fixed table names, no user input


def test_context_sees_only_its_tenant(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    assert db_rollback.execute(text("SELECT v FROM probe")).scalars().all() == ["a"]
    assert db_rollback.execute(text("SELECT id FROM organizations")).scalars().all() == [ORG_A]


def test_insert_for_other_tenant_fails_with_check(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    with pytest.raises(DBAPIError, match="row-level security"):
        db_rollback.execute(
            text("INSERT INTO probe VALUES (:i, :o, 'x')"), {"i": uuid.uuid4(), "o": ORG_B}
        )


def test_update_delete_of_other_tenant_touch_nothing(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    upd = db_rollback.execute(
        text("UPDATE probe SET v = 'z' WHERE organization_id = :o"), {"o": ORG_B}
    )
    dele = db_rollback.execute(text("DELETE FROM probe WHERE organization_id = :o"), {"o": ORG_B})
    assert (upd.rowcount, dele.rowcount) == (0, 0)  # type: ignore[attr-defined]


def test_truncate_is_denied(db_rollback: Session) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    with pytest.raises(DBAPIError, match="permission denied"):
        db_rollback.execute(text("TRUNCATE probe"))


def test_composite_fk_rejects_other_tenant_parent_like_random_id(
    db_rollback: Session, probe: dict[uuid.UUID, uuid.UUID]
) -> None:
    set_tenant_context(db_rollback, TenantContext(organization_id=ORG_A))
    errors = []
    for parent in (uuid.uuid4(), probe[ORG_B]):
        with pytest.raises(DBAPIError) as exc, db_rollback.begin_nested():
            db_rollback.execute(
                text("INSERT INTO probe_child VALUES (:o, :p)"), {"o": ORG_A, "p": parent}
            )
        errors.append(str(exc.value.orig).splitlines()[0])
    assert errors[0] == errors[1]
    assert "foreign key" in errors[0]
    db_rollback.execute(
        text("INSERT INTO probe_child VALUES (:o, :p)"), {"o": ORG_A, "p": probe[ORG_A]}
    )


SEED = """
INSERT INTO frameworks (key, name, version, jurisdiction, source, license_notes, status)
  VALUES ('fw_rls', 'R', '1', 'EU', 'src', 't', 'released');
INSERT INTO controls (key, title_es, title_en, description_es, description_en)
  VALUES ('ctl.rls', 't', 't', 'd', 'd');
"""
PER_ORG = """
INSERT INTO users (id, cognito_sub, email, email_verified) VALUES (:u, :sub, :email, true);
INSERT INTO memberships VALUES (:o, :u, 'owner');
INSERT INTO invitations (id, organization_id, email, role, token_sha256, invited_by, expires_at)
  VALUES (gen_random_uuid(), :o, 'x@example.com', 'member', :tok, :u, now() + interval '1 day');
INSERT INTO audit_events (id, organization_id, action, target_type, target_id)
  VALUES (gen_random_uuid(), :o, 'rls.seed', 'probe', 'x');
INSERT INTO evidence (id, organization_id, kind, title, source_type, created_by, collected_at)
  VALUES (:e, :o, 'attestation', 't', 'user', :u, now());
INSERT INTO evidence_controls VALUES (:e, 'ctl.rls', :o);
INSERT INTO evidence_statements (organization_id, evidence_id, submission_id,
  payload_hash, statement)
  VALUES (:o, :e, gen_random_uuid(), repeat('a', 64), 'Synthetic statement');
INSERT INTO score_snapshots (id, organization_id, framework_key, framework_version,
  catalog_version, scan_id, passed, failed, manual, not_applicable, requirement_results)
  VALUES (gen_random_uuid(), :o, 'fw_rls', '1', 'r1', gen_random_uuid(), 0, 0, 0, 0, '{}');
INSERT INTO connections (id, organization_id, provider, status, display_name, created_by)
  VALUES (gen_random_uuid(), :o, 'm365', 'pending_setup', 'rls', :u);
INSERT INTO scans (id, organization_id, connection_id, provider, trigger, status, engine,
  engine_version) VALUES (:s, :o, gen_random_uuid(), 'm365', 'user', 'queued', 'prowler', '5.49.0');
INSERT INTO scan_check_results (organization_id, scan_id, engine, check_id, status, reason)
  VALUES (:o, :s, 'prowler', 'entra_rls', 'not_evaluated', 'no_findings');
INSERT INTO findings (id, organization_id, scan_id, engine, check_id, status, severity, service,
  resource_type, resource_uid, resource_name, region, message) VALUES (gen_random_uuid(), :o, :s,
  'prowler', 'entra_rls', 'fail', 'high', 'entra', 'User', 'u-1', 'n', 'global', 'm');
INSERT INTO control_reviews (id, organization_id, control_key, status, rationale, valid_until,
  reviewed_by) VALUES (gen_random_uuid(), :o, 'ctl.rls', 'pass', 'r', current_date + 1, :u);
INSERT INTO framework_scopes (id, organization_id, framework_key, axis_values, decided_by)
  VALUES (gen_random_uuid(), :o, 'fw_rls', '{}', :u);
INSERT INTO requirement_assessments (id, organization_id, framework_key, requirement_code,
  applicability, implementation, regularly_reviewed, recorded_by) VALUES (gen_random_uuid(), :o,
  'fw_rls', 'r1', 'applies', 'implemented', true, :u);
INSERT INTO assessment_reviews (id, organization_id, framework_key, reviewer_name, reviewer_role,
  reviewed_on, conclusions, recorded_by) VALUES (gen_random_uuid(), :o, 'fw_rls', 'n', 'r',
  current_date, 'c', :u);
INSERT INTO requirement_assignments (id, organization_id, framework_key, requirement_code,
  owner_user_id, assigned_by) VALUES (gen_random_uuid(), :o, 'fw_rls', 'r1', :u, :u);
WITH r AS (INSERT INTO access_reviews (id, organization_id, title, system, created_by)
  VALUES (gen_random_uuid(), :o, 't', 's', :u) RETURNING id),
e AS (INSERT INTO access_review_entries (id, organization_id, review_id, account)
  SELECT gen_random_uuid(), :o, id, 'a' FROM r RETURNING id)
INSERT INTO access_review_decisions (id, organization_id, entry_id, decision, decided_by)
  SELECT gen_random_uuid(), :o, id, 'keep', :u FROM e;
WITH p AS (INSERT INTO policies (id, organization_id, title, location_url, review_months,
  created_by)
  VALUES (gen_random_uuid(), :o, 't', 'https://example.com/p', 12, :u) RETURNING id)
INSERT INTO policy_approvals (id, organization_id, policy_id, version, approver_name, approved_on,
  recorded_by) SELECT gen_random_uuid(), :o, id, '1', 'n', current_date, :u FROM p;
WITH c AS (INSERT INTO training_campaigns (id, organization_id, title, material_url, closes_on,
  token_sha256, created_by)
  VALUES (gen_random_uuid(), :o, 't', 'https://example.com/t', current_date, :tok, :u)
  RETURNING id)
INSERT INTO training_acknowledgements (id, organization_id, campaign_id, full_name, email)
  SELECT gen_random_uuid(), :o, id, 'n', 'n@example.com' FROM c;
WITH i AS (INSERT INTO incidents (id, organization_id, title, aware_at, significant,
  personal_data, created_by) VALUES (gen_random_uuid(), :o, 't', now(), true, false, :u)
  RETURNING id)
INSERT INTO incident_updates (id, organization_id, incident_id, kind, note, recorded_by)
  SELECT gen_random_uuid(), :o, id, 'note', 'n', :u FROM i;
WITH k AS (INSERT INTO api_tokens (id, organization_id, name, prefix, token_sha256, created_by,
  expires_at)
  VALUES (gen_random_uuid(), :o, 'n', 'atesta_xxxxx', :tok, :u, now() + interval '1 day')
  RETURNING id),
v AS (INSERT INTO evidence (id, organization_id, kind, title, source_type, source_id, created_by,
  collected_at) SELECT gen_random_uuid(), :o, 'attestation', 't', 'api', id, :u, now() FROM k
  RETURNING id, (SELECT id FROM k) AS token_id)
INSERT INTO api_ingestions (id, organization_id, token_id, evidence_id, source)
  SELECT gen_random_uuid(), :o, token_id, id, 'ci' FROM v;
INSERT INTO subscriptions (organization_id, plan) VALUES (:o, 'starter');
INSERT INTO probe_child VALUES (:o, :p);
"""


def test_every_rls_table_fails_closed_and_shows_one_tenant(
    superuser: Engine, probe: dict[uuid.UUID, uuid.UUID]
) -> None:
    """Self-seeded, rolled back: a row in every RLS table for both orgs, so an open policy on
    any table (even one other tests leave empty) fails here, whatever the test order."""
    with superuser.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql(SEED)
            for org, tag in ((ORG_A, "a"), (ORG_B, "b")):
                params = {
                    "o": org,
                    "u": uuid.uuid4(),
                    "sub": f"rls-{tag}-{uuid.uuid4()}",
                    "email": f"rls-{tag}@example.com",
                    "tok": uuid.uuid4().hex * 2,
                    "e": uuid.uuid4(),
                    "s": uuid.uuid4(),
                    "p": probe[org],
                }
                for statement in PER_ORG.strip().split(";\n"):
                    conn.execute(text(statement), params)
            session = Session(bind=conn)
            tables = rls_tables(session)
            assert {
                "organizations",
                "audit_events",
                "memberships",
                "invitations",
                "users",
                "score_snapshots",
                "evidence",
                "evidence_controls",
                "evidence_statements",
                "connections",
                "scans",
                "scan_check_results",
                "findings",
                "probe",
                "probe_child",
            } <= set(tables)
            empty = [t for t in tables if count(session, t) == 0]
            assert empty == [], "seed every RLS table, or this test proves nothing for it"
            conn.exec_driver_sql("SET LOCAL ROLE atesta_app")
            assert {t: count(session, t) for t in tables} == dict.fromkeys(tables, 0)
            set_tenant_context(session, TenantContext(organization_id=ORG_A))
            for table in (t for t in tables if t not in ("organizations", "users")):
                orgs = (
                    session.execute(
                        text(f"SELECT DISTINCT organization_id FROM {table}")  # noqa: S608  # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text - fixed table names, no user input
                    )
                    .scalars()
                    .all()
                )
                assert orgs == [ORG_A], table
        finally:
            tx.rollback()


def test_no_context_returns_zero_rows_everywhere(db_rollback: Session) -> None:
    tables = rls_tables(db_rollback)
    assert {"organizations", "audit_events", "probe", "probe_child"} <= set(tables)
    assert {t: count(db_rollback, t) for t in tables} == dict.fromkeys(tables, 0)


def test_pooled_connection_never_carries_a_tenant(db_commit: sessionmaker[Session]) -> None:
    with db_commit() as first:
        set_tenant_context(first, TenantContext(subject="s", organization_id=ORG_A))
        pid = first.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert count(first, "probe") == 1
        first.commit()
    with db_commit() as second:
        assert second.execute(text("SELECT pg_backend_pid()")).scalar_one() == pid
        values = [
            second.execute(text("SELECT current_setting(:n, true)"), {"n": n}).scalar_one()
            for n in SETTINGS
        ]
        assert all(v in (None, "") for v in values)
        assert all(count(second, t) == 0 for t in rls_tables(second))
