"""Public interface of the evidence module. Planned: store_evidence, build_pack."""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from fastapi import FastAPI
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import active_control_keys, control_is_active
from atesta_api.modules.evidence.models import Evidence, EvidenceControl

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def install_evidence(app: FastAPI) -> None:
    from atesta_api.modules.evidence.ingest import router as ingest_router
    from atesta_api.modules.evidence.routes import router

    app.include_router(router)
    app.include_router(ingest_router)


def statements_in_org(
    session: Session, organization_id: uuid.UUID, evidence_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    """The given evidence ids that are statements of this organization (requirement register)."""
    ids = set(evidence_ids)
    if not ids:
        return set()
    from atesta_api.modules.evidence.models import EvidenceStatement

    rows = session.scalars(
        select(EvidenceStatement.evidence_id).where(
            EvidenceStatement.organization_id == organization_id,
            EvidenceStatement.evidence_id.in_(ids),
        )
    )
    return set(rows)


@dataclass(frozen=True, slots=True)
class StatementView:
    """An evidence statement as an auditor reads it (auditor-dossier spec)."""

    title: str
    statement: str
    reference_url: str | None
    collected_at: datetime
    source_type: str


def statements_by_control(
    session: Session, organization_id: uuid.UUID, control_keys: Iterable[str], limit: int = 20
) -> dict[str, list[StatementView]]:
    """The newest statements linked to each control, at most `limit` per control."""
    from atesta_api.modules.evidence.models import EvidenceStatement

    keys = set(control_keys)
    if not keys:
        return {}
    rows = session.execute(
        select(EvidenceControl.control_key, Evidence, EvidenceStatement)
        .join(
            Evidence,
            (Evidence.organization_id == EvidenceControl.organization_id)
            & (Evidence.id == EvidenceControl.evidence_id),
        )
        .join(
            EvidenceStatement,
            (EvidenceStatement.organization_id == Evidence.organization_id)
            & (EvidenceStatement.evidence_id == Evidence.id),
        )
        .where(
            EvidenceControl.organization_id == organization_id,
            EvidenceControl.control_key.in_(keys),
        )
        .order_by(EvidenceControl.control_key, Evidence.collected_at.desc(), Evidence.id)
    ).tuples()
    out: dict[str, list[StatementView]] = {}
    for key, evidence, statement in rows:
        found = out.setdefault(key, [])
        if len(found) < limit:
            found.append(
                StatementView(
                    title=evidence.title,
                    statement=statement.statement,
                    reference_url=statement.reference_url,
                    collected_at=evidence.collected_at,
                    source_type=evidence.source_type,
                )
            )
    return out


def evidence_count(session: Session, organization_id: uuid.UUID) -> int:
    """Count tenant records without loading document contents or storage metadata."""
    return session.execute(
        select(func.count())
        .select_from(Evidence)
        .where(Evidence.organization_id == organization_id)
    ).scalar_one()


def storage_key_for(organization_id: uuid.UUID, evidence_id: uuid.UUID, filename: str) -> str:
    """Server-built S3 key under the tenant prefix (ADR-004). Never accept a client key."""
    name = _UNSAFE.sub("_", filename).strip("._") or "file"
    return f"{organization_id}/evidence/{evidence_id}/{name[:120]}"


def link_evidence(
    session: Session, organization_id: uuid.UUID, evidence_id: uuid.UUID, control_key: str
) -> None:
    """Link evidence to an active control; the control key is checked through compliance.api."""
    if not control_is_active(session, control_key):
        raise ValueError(f"unknown or retired control: {control_key}")
    session.add(
        EvidenceControl(
            organization_id=organization_id, evidence_id=evidence_id, control_key=control_key
        )
    )
    session.flush()


def record_attestation(
    session: Session,
    *,
    organization_id: uuid.UUID,
    author: uuid.UUID,
    control_key: str,
    title: str,
    statement: str,
    reference_url: str | None = None,
    source_type: str = "user",
    source_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """A statement written by a recorded routine (recorded-routines spec) or an API token
    (evidence-ingestion-api spec, source "api" naming the token). It is linked to the control
    when the control is active in the catalog; the statement itself is always kept."""
    import hashlib
    import json

    from atesta_api.modules.evidence.models import EvidenceStatement

    evidence_id = uuid.uuid4()
    session.add(
        Evidence(
            id=evidence_id,
            organization_id=organization_id,
            kind="attestation",
            title=title[:200],
            source_type=source_type,
            source_id=source_id,
            created_by=author,
            collected_at=datetime.now().astimezone(),
        )
    )
    session.flush()
    payload = {
        "control": control_key,
        "title": title,
        "statement": statement,
        "author": str(author),
    }
    session.add(
        EvidenceStatement(
            organization_id=organization_id,
            evidence_id=evidence_id,
            submission_id=uuid.uuid4(),
            payload_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
            statement=statement,
            reference_url=reference_url,
        )
    )
    if control_is_active(session, control_key):
        session.add(
            EvidenceControl(
                organization_id=organization_id, evidence_id=evidence_id, control_key=control_key
            )
        )
    session.flush()
    return evidence_id


@dataclass(frozen=True, slots=True)
class ScanOutputFile:
    storage_key: str  # under <org_id>/scans/<scan_id>/attempt-<n>/out/, checked by the table
    sha256: str
    size_bytes: int
    media_type: str


def register_scan_output(
    session: Session,
    *,
    organization_id: uuid.UUID,
    scan_id: uuid.UUID,
    files: Sequence[ScanOutputFile],
    control_keys: Iterable[str],
    collected_at: datetime,
) -> list[uuid.UUID]:
    """Scan output files as evidence, each linked to every given control (active ones only)."""
    keys = set(control_keys)
    unknown = keys - active_control_keys(session, keys)
    if unknown:
        raise ValueError(f"unknown or retired controls: {sorted(unknown)}")
    ids = [uuid.uuid4() for _ in files]
    if not files:
        return ids
    session.execute(
        insert(Evidence),
        [
            {
                "id": evidence_id,
                "organization_id": organization_id,
                "kind": "scan_output",
                "title": f.storage_key.rsplit("/", 1)[1],
                "storage_key": f.storage_key,
                "sha256": f.sha256,
                "media_type": f.media_type,
                "size_bytes": f.size_bytes,
                "source_type": "scan",
                "source_id": scan_id,
                "collected_at": collected_at,
            }
            for evidence_id, f in zip(ids, files, strict=True)
        ],
    )
    links = [
        {"organization_id": organization_id, "evidence_id": evidence_id, "control_key": key}
        for evidence_id in ids
        for key in sorted(keys)
    ]
    if links:
        session.execute(insert(EvidenceControl), links)
    return ids
