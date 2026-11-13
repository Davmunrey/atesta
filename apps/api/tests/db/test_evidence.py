"""Evidence: integrity CHECKs, tenant-bound storage keys, composite links (control-model spec)."""

import uuid
from typing import Any

import pytest
from atesta_api.modules.evidence.api import link_evidence, storage_key_for
from atesta_api.modules.identity.api import ContextReason, enter_org_context
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .conftest import ORG_A, ORG_B

SHA = "a" * 64
INSERT = text(
    "INSERT INTO evidence (id, organization_id, kind, title, storage_key, sha256, media_type,"
    " size_bytes, source_type, source_id, created_by, collected_at) VALUES (:id, :org, :kind,"
    " 't', :key, :sha, :media, :size, :source, :source_id, :author, now())"
)


def row(**overrides: Any) -> dict[str, Any]:
    evidence_id = uuid.uuid4()
    base = {
        "id": evidence_id,
        "org": ORG_A,
        "kind": "document",
        "key": storage_key_for(ORG_A, evidence_id, "política de acceso.pdf"),
        "sha": SHA,
        "media": "application/pdf",
        "size": 10,
        "source": "upload",
        "source_id": None,
        "author": uuid.uuid4(),
    }
    return {**base, **overrides}


@pytest.fixture
def tx(db_rollback: Session) -> Session:
    enter_org_context(db_rollback, ORG_A, ContextReason.MEMBERSHIP)
    return db_rollback


@pytest.fixture(scope="module", autouse=True)
def controls(superuser: Engine, probe: object) -> None:
    with superuser.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO controls (key, title_es, title_en, description_es, description_en,"
            " retired_at) VALUES ('ctl.ev', 't', 't', 'd', 'd', NULL),"
            " ('ctl.ev_old', 't', 't', 'd', 'd', now()) ON CONFLICT DO NOTHING"
        )


ACCEPTED = {
    "document": {},
    "attestation without file": {
        "kind": "attestation",
        "key": None,
        "sha": None,
        "media": None,
        "size": None,
    },
    "scan output": {
        "kind": "scan_output",
        "source": "scan",
        "source_id": uuid.uuid4(),
        "author": None,
    },
}
REJECTED = {
    "file without hash": ({"sha": None}, "file_described"),
    "attestation file without size": ({"kind": "attestation", "size": None}, "file_described"),
    "hash without file": ({"key": None, "media": None, "size": None}, "file_described"),
    "document without file": (
        {"key": None, "sha": None, "media": None, "size": None},
        "file_required",
    ),
    "malformed hash": ({"sha": "A" * 64}, "sha256_format"),
    "scan without scan id": (
        {"kind": "scan_output", "source": "scan", "author": None},
        "scan_named",
    ),
    "upload without author": ({"author": None}, "author_named"),
    "other tenant prefix": ({"key": f"{ORG_B}/evidence/x/f.pdf"}, "tenant_prefix"),
    "dot-dot segment": ({"key": f"{ORG_A}/../{ORG_B}/f.pdf"}, "tenant_prefix"),
    "empty segment": ({"key": f"{ORG_A}//f.pdf"}, "tenant_prefix"),
    "bad kind": ({"kind": "photo"}, "ck_evidence_kind"),
}


@pytest.mark.parametrize("name", sorted(ACCEPTED))
def test_valid_evidence_is_accepted(tx: Session, name: str) -> None:
    tx.execute(INSERT, row(**ACCEPTED[name]))


@pytest.mark.parametrize("name", sorted(REJECTED))
def test_invalid_evidence_is_rejected(tx: Session, name: str) -> None:
    overrides, constraint = REJECTED[name]
    with pytest.raises(DBAPIError, match=constraint):
        tx.execute(INSERT, row(**overrides))


def test_links_are_tenant_bound_and_validated(tx: Session, superuser: Engine) -> None:
    other = row(org=ORG_B, key=None, kind="attestation", sha=None, media=None, size=None)
    with superuser.begin() as conn:
        conn.execute(INSERT, other)
    mine = row()
    tx.execute(INSERT, mine)
    link_evidence(tx, ORG_A, mine["id"], "ctl.ev")
    errors = []
    for evidence_id in (other["id"], uuid.uuid4()):  # B's real id must look like a random one
        with pytest.raises(DBAPIError) as exc, tx.begin_nested():
            link_evidence(tx, ORG_A, evidence_id, "ctl.ev")
        errors.append(str(exc.value.orig).splitlines()[0])
    assert errors[0] == errors[1]
    with pytest.raises(ValueError, match="retired"):
        link_evidence(tx, ORG_A, mine["id"], "ctl.ev_old")


@pytest.mark.parametrize("table", ["evidence", "evidence_controls"])
def test_append_only(tx: Session, table: str) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        tx.execute(text(f"DELETE FROM {table}"))  # noqa: S608


def test_storage_key_is_safe() -> None:
    evidence_id = uuid.uuid4()
    key = storage_key_for(ORG_A, evidence_id, "../../etc/passwd")
    assert key == f"{ORG_A}/evidence/{evidence_id}/etc_passwd"
