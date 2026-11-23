"""Training acknowledgements (recorded-routines spec, part B).

Admins share a secret link; anyone with it confirms they read the material, without an account.
The token travels in the URL fragment and the request body, never in a query string, and the API
keeps only its SHA-256. The public endpoints read the campaign through the named policy
training_token_read, then write in the organization's context (ADR-012 amendment 4).
"""

import secrets
import uuid
from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import TrainingAcknowledgement, TrainingCampaign
from atesta_api.modules.compliance.text import filled
from atesta_api.modules.evidence.api import record_attestation
from atesta_api.modules.identity.api import (
    ContextReason,
    Member,
    QueryFreeRoute,
    Role,
    enter_org_context,
    enter_training_link_context,
    normalize_email,
    person,
    require_member,
    require_role,
    token_hash,
)
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.i18n import Locale, message

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])
public_router = APIRouter(
    prefix="/api/v1/training", tags=["compliance"], route_class=QueryFreeRoute
)

TRAINING_CONTROL = "ctl.people_awareness"
MAX_ACKNOWLEDGEMENTS = 1000
_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


def _today() -> date:
    return datetime.now().astimezone().date()


class CampaignIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    material_url: str = Field(min_length=9, max_length=2000, pattern=r"^https://\S+$")
    closes_on: date

    @field_validator("title")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)

    @field_validator("closes_on")
    @classmethod
    def not_past(cls, value: date) -> date:
        if value < _today():
            raise ValueError("the closing date has passed")
        return value


class CampaignOut(BaseModel):
    id: uuid.UUID
    title: str
    material_url: str
    closes_on: date
    created_at: datetime
    closed_at: datetime | None
    acknowledged: int


class CreatedCampaign(CampaignOut):
    link: str  # shown once; the API keeps only the SHA-256 of the token


class AcknowledgementOut(BaseModel):
    full_name: str
    email: str
    acknowledged_at: datetime


class CampaignDetail(CampaignOut):
    acknowledgements: list[AcknowledgementOut]


def _counts(session: Session, org: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = session.execute(
        select(TrainingAcknowledgement.campaign_id, func.count())
        .where(TrainingAcknowledgement.organization_id == org)
        .group_by(TrainingAcknowledgement.campaign_id)
    )
    return {campaign: count for campaign, count in rows.tuples()}


def _out(row: TrainingCampaign, count: int) -> CampaignOut:
    return CampaignOut(
        id=row.id,
        title=row.title,
        material_url=row.material_url,
        closes_on=row.closes_on,
        created_at=row.created_at,
        closed_at=row.closed_at,
        acknowledged=count,
    )


def _campaign(session: Session, org: uuid.UUID, campaign_id: uuid.UUID) -> TrainingCampaign:
    row = session.scalar(
        select(TrainingCampaign).where(
            TrainingCampaign.organization_id == org, TrainingCampaign.id == campaign_id
        )
    )
    if row is None:
        raise _error(404, "compliance.training_not_found")
    return row


def _acknowledgements(
    session: Session, org: uuid.UUID, campaign_id: uuid.UUID
) -> list[AcknowledgementOut]:
    rows = session.scalars(
        select(TrainingAcknowledgement)
        .where(
            TrainingAcknowledgement.organization_id == org,
            TrainingAcknowledgement.campaign_id == campaign_id,
        )
        .order_by(TrainingAcknowledgement.acknowledged_at, TrainingAcknowledgement.id)
    )
    return [AcknowledgementOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/training-campaigns", status_code=201)
def create_campaign(
    body: CampaignIn,
    request: Request,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> CreatedCampaign:
    token = secrets.token_urlsafe(32)
    campaign = TrainingCampaign(
        organization_id=member.organization_id,
        title=body.title,
        material_url=body.material_url,
        closes_on=body.closes_on,
        token_sha256=token_hash(token),
        created_by=member.user_id,
    )
    session.add(campaign)
    session.flush()
    session.refresh(campaign)
    record(
        session,
        organization_id=member.organization_id,
        action="training.created",
        target_type="training_campaign",
        target_id=str(campaign.id),
        actor_user_id=member.user_id,
    )
    link = f"{request.app.state.web_base_url}/training#token={token}"  # fragment: never logged
    return CreatedCampaign(**_out(campaign, 0).model_dump(), link=link)


@router.get("/training-campaigns")
def list_campaigns(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[CampaignOut]:
    org = member.organization_id
    counts = _counts(session, org)
    rows = session.scalars(
        select(TrainingCampaign)
        .where(TrainingCampaign.organization_id == org)
        .order_by(TrainingCampaign.created_at.desc(), TrainingCampaign.id)
    )
    return [_out(r, counts.get(r.id, 0)) for r in rows]


@router.get("/training-campaigns/{campaign_id}")
def read_campaign(
    campaign_id: uuid.UUID, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> CampaignDetail:
    org = member.organization_id
    campaign = _campaign(session, org, campaign_id)
    people = _acknowledgements(session, org, campaign_id)
    return CampaignDetail(**_out(campaign, len(people)).model_dump(), acknowledgements=people)


@router.post("/training-campaigns/{campaign_id}/close")
def close_campaign(
    campaign_id: uuid.UUID,
    member: Annotated[Member, Depends(require_role(Role.ADMIN))],
    session: DbSession,
) -> CampaignDetail:
    org = member.organization_id
    campaign = _campaign(session, org, campaign_id)
    if campaign.closed_at is not None:
        raise _error(409, "compliance.training_closed")
    now = datetime.now(UTC)
    session.execute(
        update(TrainingCampaign)
        .where(
            TrainingCampaign.organization_id == org,
            TrainingCampaign.id == campaign_id,
            TrainingCampaign.closed_at.is_(None),
        )
        .values(closed_at=now, closed_by=member.user_id)
    )
    people = _acknowledgements(session, org, campaign_id)
    email, locale = person(session, member.user_id)
    lang: Locale = "en" if locale == "en" else "es"
    record_attestation(
        session,
        organization_id=org,
        author=member.user_id,
        control_key=TRAINING_CONTROL,
        title=message(lang, "routines.training_title").format(title=campaign.title),
        statement=message(lang, "routines.training_closed").format(
            title=campaign.title, count=len(people), date=now.date().isoformat(), email=email
        ),
        reference_url=campaign.material_url,
    )
    record(
        session,
        organization_id=org,
        action="training.closed",
        target_type="training_campaign",
        target_id=str(campaign_id),
        actor_user_id=member.user_id,
        metadata={"acknowledged": len(people)},
    )
    session.refresh(campaign)
    return CampaignDetail(**_out(campaign, len(people)).model_dump(), acknowledgements=people)


# --- the public link ------------------------------------------------------------------------


class LinkIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class AcknowledgeIn(LinkIn):
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=_EMAIL)

    @field_validator("full_name")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)

    @field_validator("email")
    @classmethod
    def fold(cls, value: str) -> str:
        return normalize_email(value)


class PublicCampaign(BaseModel):
    title: str
    material_url: str
    closes_on: date


class Acknowledged(BaseModel):
    recorded: bool  # false when this email had already confirmed


def _open_by_token(session: Session, token: str) -> TrainingCampaign:
    enter_training_link_context(session, token_hash(token))
    campaign = session.scalar(
        select(TrainingCampaign).where(TrainingCampaign.token_sha256 == token_hash(token))
    )
    if campaign is None:
        raise _error(404, "compliance.training_link_invalid")
    if campaign.closed_at is not None or campaign.closes_on < _today():
        raise _error(410, "compliance.training_closed")
    return campaign


@public_router.post("/link")
def read_link(body: LinkIn, session: DbSession) -> PublicCampaign:
    campaign = _open_by_token(session, body.token)
    return PublicCampaign(
        title=campaign.title, material_url=campaign.material_url, closes_on=campaign.closes_on
    )


@public_router.post("/acknowledge")
def acknowledge(body: AcknowledgeIn, session: DbSession) -> Acknowledged:
    campaign = _open_by_token(session, body.token)
    org = campaign.organization_id
    enter_org_context(session, org, ContextReason.TRAINING_LINK)
    # Lock the campaign so concurrent confirmations cannot pass the cap together.
    session.execute(
        select(TrainingCampaign.id)
        .where(TrainingCampaign.organization_id == org, TrainingCampaign.id == campaign.id)
        .with_for_update()
    )
    mine = TrainingAcknowledgement.campaign_id == campaign.id
    already = session.scalar(
        select(TrainingAcknowledgement.id).where(
            TrainingAcknowledgement.organization_id == org,
            mine,
            TrainingAcknowledgement.email == body.email,
        )
    )
    if already is not None:
        return Acknowledged(recorded=False)
    count = session.scalar(
        select(func.count()).where(TrainingAcknowledgement.organization_id == org, mine)
    )
    if (count or 0) >= MAX_ACKNOWLEDGEMENTS:
        raise _error(409, "compliance.training_full")
    session.add(
        TrainingAcknowledgement(
            organization_id=org,
            campaign_id=campaign.id,
            full_name=body.full_name,
            email=body.email,
        )
    )
    session.flush()
    record(
        session,
        organization_id=org,
        action="training.acknowledged",
        target_type="training_campaign",
        target_id=str(campaign.id),
    )
    return Acknowledged(recorded=True)


def unclosed_campaigns(session: Session, org: uuid.UUID) -> list[TrainingCampaign]:
    """Open campaigns past their closing date: a reminder to close them and record evidence."""
    return list(
        session.scalars(
            select(TrainingCampaign).where(
                TrainingCampaign.organization_id == org,
                TrainingCampaign.closed_at.is_(None),
                TrainingCampaign.closes_on < _today(),
            )
        )
    )
