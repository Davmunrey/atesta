"""Public interface of the evidence module. Planned: store_evidence, build_pack."""

import re
import uuid

from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import control_is_active
from atesta_api.modules.evidence.models import EvidenceControl

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
