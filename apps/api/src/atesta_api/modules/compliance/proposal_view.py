"""Pending self-assessment proposals as the register shows them (mcp-server spec, #339).

Free text is customer content, returned to members and never logged (rule 2).
"""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import AssessmentProposal
from atesta_api.modules.identity.api import token_labels


class PendingProposal(BaseModel):
    id: uuid.UUID
    applicability: Literal["applies", "not_applicable"]
    implementation: Literal["not_implemented", "partially_implemented", "implemented"]
    regularly_reviewed: bool
    justification: str
    performed_by: str
    performed_on: date | None
    evidence_statement_ids: list[uuid.UUID]
    notes: str
    rationale: str
    proposed_at: datetime
    token_name: str
    token_prefix: str


def pending_proposals(
    session: Session, organization_id: uuid.UUID, framework_key: str
) -> dict[str, PendingProposal]:
    rows = list(
        session.scalars(
            select(AssessmentProposal).where(
                AssessmentProposal.organization_id == organization_id,
                AssessmentProposal.framework_key == framework_key,
                AssessmentProposal.status == "pending",
            )
        )
    )
    labels = token_labels(session, organization_id, {r.token_id for r in rows})
    return {
        r.requirement_code: PendingProposal.model_validate(
            {
                **{f: getattr(r, f) for f in PendingProposal.model_fields if hasattr(r, f)},
                "token_name": labels.get(r.token_id, ("", ""))[0],
                "token_prefix": labels.get(r.token_id, ("", ""))[1],
            }
        )
        for r in rows
    }
