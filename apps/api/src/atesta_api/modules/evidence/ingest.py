"""Evidence ingestion through an API key (evidence-ingestion-api and api-keys-v2 specs).

A customer's own tool records an evidence statement on a common control. The key needs the
scope evidence:write, checked by identity.api. The statement's author is the admin who created
the key, its source is "api" and it names the key. Retries with the same external id write
nothing.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from atesta_api.modules.compliance.api import control_is_active
from atesta_api.modules.evidence.api import record_attestation, refuse_credential_link
from atesta_api.modules.evidence.models import ApiIngestion
from atesta_api.modules.identity.api import ApiCaller, QueryFreeRoute, require_scope
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession

router = APIRouter(prefix="/api/v1/ingest", tags=["evidence"], route_class=QueryFreeRoute)


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


def _filled(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("the text is empty")
    return cleaned


class IngestIn(BaseModel):
    control: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=4000)
    source: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$")
    reference_url: str | None = Field(default=None, max_length=2000, pattern=r"^https://\S+$")
    external_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("title", "statement")
    @classmethod
    def tidy(cls, value: str) -> str:
        return _filled(value)

    @field_validator("reference_url")
    @classmethod
    def no_credential_link(cls, value: str | None) -> str | None:
        """Never store a link that is itself a credential (rule 2, #256)."""
        return None if value is None else refuse_credential_link(value)


class Ingested(BaseModel):
    evidence_id: uuid.UUID
    duplicate: bool


@router.post("/evidence", status_code=201)
def ingest_evidence(
    body: IngestIn,
    caller: Annotated[ApiCaller, Depends(require_scope("evidence:write"))],
    response: Response,
    session: DbSession,
) -> Ingested:
    org = caller.organization_id
    if body.external_id is not None:
        seen = session.scalar(
            select(ApiIngestion.evidence_id).where(
                ApiIngestion.organization_id == org,
                ApiIngestion.token_id == caller.token_id,
                ApiIngestion.external_id == body.external_id,
            )
        )
        if seen is not None:
            response.status_code = 200
            return Ingested(evidence_id=seen, duplicate=True)
    if not control_is_active(session, body.control):
        raise _error(422, "evidence.control_not_found")
    evidence_id = record_attestation(
        session,
        organization_id=org,
        author=caller.created_by,
        control_key=body.control,
        title=body.title,
        statement=body.statement,
        reference_url=body.reference_url,
        source_type="api",
        source_id=caller.token_id,
    )
    session.add(
        ApiIngestion(
            organization_id=org,
            token_id=caller.token_id,
            evidence_id=evidence_id,
            source=body.source,
            external_id=body.external_id,
        )
    )
    session.flush()
    record(
        session,
        organization_id=org,
        action="evidence.ingested",
        target_type="evidence",
        target_id=str(evidence_id),
        actor_user_id=caller.created_by,
        metadata={
            "via": "api_token",
            "token": caller.prefix,
            "token_id": str(caller.token_id),
            "source": body.source,
            "control": body.control,
        },
    )
    return Ingested(evidence_id=evidence_id, duplicate=False)
