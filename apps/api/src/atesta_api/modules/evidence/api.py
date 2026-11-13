"""Public interface of the evidence module. Planned: store_evidence, build_pack."""

import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import active_control_keys, control_is_active
from atesta_api.modules.evidence.models import Evidence, EvidenceControl

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


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
