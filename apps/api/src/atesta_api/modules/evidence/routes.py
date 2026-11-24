"""Tenant-bound declared evidence with atomic auditing and retry-safe submissions."""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.api import control_is_visible
from atesta_api.modules.evidence.files import file_out, file_uploads
from atesta_api.modules.evidence.models import Evidence, EvidenceControl, EvidenceStatement
from atesta_api.modules.evidence.schemas import EvidenceOut, EvidencePage, StatementIn
from atesta_api.modules.identity.api import Member, require_member
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/controls/{control_key}/evidence", tags=["evidence"]
)


def visible(session: Session, key: str) -> None:
    if not control_is_visible(session, key):
        raise HTTPException(404, detail={"code": "evidence.control_not_found"})


def output(row: Evidence, statement: EvidenceStatement | None) -> EvidenceOut:
    return EvidenceOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        created_by=row.created_by,
        created_at=row.created_at.astimezone(UTC),
        collected_at=row.collected_at.astimezone(UTC),
        statement=statement.statement if statement else None,
        reference_url=statement.reference_url if statement else None,
        file=file_out(row),
    )


@router.get("")
def list_evidence(
    control_key: str,
    request: Request,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> EvidencePage:
    visible(session, control_key)
    linked = and_(
        EvidenceControl.organization_id == member.organization_id,
        EvidenceControl.control_key == control_key,
    )
    total = session.scalar(select(func.count()).select_from(EvidenceControl).where(linked)) or 0
    rows = session.execute(
        select(Evidence, EvidenceStatement)
        .join(
            EvidenceControl,
            and_(
                Evidence.id == EvidenceControl.evidence_id,
                Evidence.organization_id == EvidenceControl.organization_id,
            ),
        )
        .outerjoin(
            EvidenceStatement,
            and_(
                EvidenceStatement.evidence_id == Evidence.id,
                EvidenceStatement.organization_id == Evidence.organization_id,
            ),
        )
        .where(linked)
        .order_by(Evidence.created_at.desc(), Evidence.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return EvidencePage(
        total=total,
        items=[output(row, statement) for row, statement in rows],
        file_uploads=file_uploads(request),
    )


@router.post("", status_code=201)
def record_statement(
    control_key: str,
    body: StatementIn,
    member: Annotated[Member, Depends(require_member)],
    session: DbSession,
) -> EvidenceOut:
    visible(session, control_key)
    org = member.organization_id
    payload = {
        **body.model_dump(mode="json"),
        "control": control_key,
        "author": str(member.user_id),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    # Serialize the same submission across controls, so a conflicting retry returns 409.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"evidence:{org}:{body.submission_id}"},
    )
    existing = session.scalar(
        select(EvidenceStatement).where(
            EvidenceStatement.organization_id == org,
            EvidenceStatement.submission_id == body.submission_id,
        )
    )
    if existing:
        if existing.payload_hash != digest:
            raise HTTPException(409, detail={"code": "evidence.submission_conflict"})
        row = session.execute(
            select(Evidence).where(
                Evidence.organization_id == org,
                Evidence.id == existing.evidence_id,
            )
        ).scalar_one()
        return output(row, existing)
    row = Evidence(
        id=uuid.uuid4(),
        organization_id=org,
        kind="attestation",
        title=body.title,
        source_type="user",
        created_by=member.user_id,
        collected_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    statement = EvidenceStatement(
        organization_id=org,
        evidence_id=row.id,
        submission_id=body.submission_id,
        payload_hash=digest,
        statement=body.statement,
        reference_url=body.reference_url,
    )
    session.add_all(
        [
            statement,
            EvidenceControl(organization_id=org, evidence_id=row.id, control_key=control_key),
        ]
    )
    record(
        session,
        organization_id=org,
        action="evidence.statement_recorded",
        target_type="evidence",
        target_id=str(row.id),
        actor_user_id=member.user_id,
        metadata={"control_key": control_key},
    )
    return output(row, statement)
