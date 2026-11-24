"""Connections: no secret, no other org's secret, one tenant pin (scanner-connectors spec)."""

import uuid
from typing import Any

import pytest
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

INSERT = text(
    "INSERT INTO connections (id, organization_id, provider, status, display_name,"
    " external_tenant_id, ms_tenant_id, credential_ref, verifier_credential_ref, google_client_id,"
    " google_verifier_client_id, google_unique_id, google_verifier_unique_id, google_subject_email,"
    " granted, created_by, revoked_at) VALUES (:id, :org, :provider, :status, :name, :tenant,"
    " :ms_tenant, :ref, :verifier_ref, :client, :verifier_client, :unique, :verifier_unique,"
    " :subject, CAST(:granted AS jsonb), :by, :revoked)"
)
TENANT = "11111111-1111-4111-8111-111111111111"
ARN = "aws-sm:arn:aws:secretsmanager:eu-south-2:123456789012:secret:atesta/dev"


def m365(**overrides: Any) -> dict[str, Any]:
    base = {
        "id": uuid.uuid4(),
        "org": ORG_A,
        "provider": "m365",
        "status": "pending_setup",
        "name": "Contoso M365",
        "tenant": None,
        "ms_tenant": None,
        "ref": None,
        "verifier_ref": None,
        "client": None,
        "verifier_client": None,
        "unique": None,
        "verifier_unique": None,
        "subject": None,
        "granted": "{}",
        "by": uuid.uuid4(),
        "revoked": None,
    }
    return {**base, **overrides}


def google(**overrides: Any) -> dict[str, Any]:
    active = {
        "provider": "google_workspace",
        "status": "active",
        "name": "Contoso Workspace",
        "tenant": "C0fixture1",
        "ref": f"local:google-{ORG_A}",
        "verifier_ref": f"local:google-verifier-{ORG_A}",
        "client": "111111111111111111111",
        "verifier_client": "222222222222222222222",
        "unique": "333333333333333333333",  # IAM uniqueIds (issue 398)
        "verifier_unique": "444444444444444444444",
        "subject": "admin@contoso.example",
    }
    return m365(**{**active, **overrides})


@pytest.fixture
def tx(db_rollback: Session) -> Session:
    enter_org_context(db_rollback, ORG_A, ContextReason.JOB)
    return db_rollback


ACCEPTED = {
    "m365 being set up": m365(),
    "m365 active": m365(status="active", tenant=TENANT, ms_tenant=TENANT),
    "google active, local refs": google(),
    "google active, Secrets Manager refs": google(
        ref=f"{ARN}/google/{ORG_A}-AbC123", verifier_ref=f"{ARN}/google-verifier/{ORG_A}-x9Y8z7"
    ),
    "google being provisioned, no refs yet": google(
        status="pending_provisioning", tenant=None, ref=None, verifier_ref=None, subject=None
    ),
}


@pytest.mark.parametrize("name", sorted(ACCEPTED))
def test_valid_connections_are_accepted(tx: Session, name: str) -> None:
    tx.execute(INSERT, ACCEPTED[name])


KEY_MATERIAL = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7"  # base64 key body
REJECTED = {
    "unknown provider": (m365(provider="aws"), "ck_connections_provider"),
    "unknown status": (m365(status="paused"), "ck_connections_status"),
    "blank display name": (m365(name="  "), "ck_connections_display_name_filled"),
    "granted not an object": (m365(granted="[]"), "ck_connections_granted_object"),
    "m365 with a credential ref": (m365(ref="local:m365-cert"), "ck_connections_m365_no_refs"),
    "m365 tenant not a GUID": (m365(tenant="contoso.com"), "ck_connections_m365_tenant_guid"),
    "ms tenant not a GUID": (m365(ms_tenant="Contoso"), "ck_connections_ms_tenant_guid"),
    "active without a tenant": (m365(status="active"), "ck_connections_active_has_tenant"),
    "a key instead of a ref": (google(ref=KEY_MATERIAL), "ck_connections_credential_ref_format"),
    "secret in another region": (
        google(ref=f"{ARN.replace('eu-south-2', 'eu-west-1')}/google/{ORG_A}-AbC123"),
        "ck_connections_credential_ref_format",
    ),
    "another org's Google secret": (
        google(ref=f"local:google-{ORG_B}"),
        "ck_connections_google_ref_in_tenant",
    ),
    "another org's Secrets Manager secret": (
        google(ref=f"{ARN}/google/{ORG_B}-AbC123"),
        "ck_connections_google_ref_in_tenant",
    ),
    "the verifier key used as the scan key": (
        google(ref=f"local:google-verifier-{ORG_A}"),
        "ck_connections_google_ref_in_tenant",
    ),
    "the scan key used as the verifier key": (
        google(verifier_ref=f"local:google-{ORG_A}"),
        "ck_connections_google_verifier_ref_in_tenant",
    ),
    "active google without a subject": (
        google(subject=None),
        "ck_connections_active_google_complete",
    ),
    "active google without the verifier": (
        google(verifier_ref=None, verifier_client=None),
        "ck_connections_active_google_complete",
    ),
}


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_invalid_connections_are_rejected(tx: Session, name: str) -> None:
    row, constraint = REJECTED[name]
    with pytest.raises(DBAPIError, match=constraint):
        tx.execute(INSERT, row)


def test_one_live_connection_per_tenant(tx: Session) -> None:
    tx.execute(INSERT, m365(status="active", tenant=TENANT))
    with pytest.raises(DBAPIError, match="uq_connections_one_live_per_tenant"), tx.begin_nested():
        tx.execute(INSERT, m365(status="active", tenant=TENANT))
    tx.execute(INSERT, m365(status="revoked", tenant=TENANT, revoked=text_now(tx)))


def text_now(session: Session) -> object:
    return session.execute(text("SELECT now()")).scalar_one()


def test_the_tenant_pin_never_changes_once_set(tx: Session) -> None:
    row = m365()
    tx.execute(INSERT, row)
    pin = text("UPDATE connections SET external_tenant_id = :t WHERE id = :id")
    tx.execute(pin, {"t": TENANT, "id": row["id"]})  # first verification sets it
    other = "33333333-3333-4333-8333-333333333333"
    with pytest.raises(DBAPIError, match="immutable"), tx.begin_nested():
        tx.execute(pin, {"t": other, "id": row["id"]})
    with pytest.raises(DBAPIError, match="immutable"), tx.begin_nested():
        tx.execute(pin, {"t": None, "id": row["id"]})
    with pytest.raises(DBAPIError, match="immutable"), tx.begin_nested():
        tx.execute(
            text("UPDATE connections SET provider = 'google_workspace' WHERE id = :id"),
            {"id": row["id"]},
        )
    tx.execute(
        text("UPDATE connections SET status = 'disconnected' WHERE id = :id"), {"id": row["id"]}
    )


def test_connections_are_never_deleted(tx: Session) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        tx.execute(text("DELETE FROM connections"))


def test_a_secrets_manager_name_is_at_most_512_characters(tx: Session) -> None:
    # The spec's {1,512} name, as a length bound: Postgres caps regex repetition at 255.
    prefix = "aws-sm:arn:aws:secretsmanager:eu-south-2:123456789012:secret:"
    suffix = f"/google/{ORG_A}-AbC123"  # this org's Google secret

    def ref(name_length: int) -> str:
        env = "d" * (name_length - len("atesta/") - len(suffix))
        return f"{prefix}atesta/{env}{suffix}"

    assert len(ref(512)) - len(prefix) == 512
    tx.execute(INSERT, google(ref=ref(512)))
    with pytest.raises(DBAPIError, match="ck_connections_credential_ref_format"):
        tx.execute(INSERT, google(ref=ref(513), tenant="C0fixture2"))
