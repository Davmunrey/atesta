"""Incident register with reporting clocks (recorded-routines spec, part B).

Clocks are framework-pack content (`reporting_clocks`, rule 9), read from the active catalog;
atesta_core.clocks computes their states. Atesta shows due times; whether a notification is owed,
and to whom, is the organization's decision (ADR-005).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast

from atesta_core.clocks import ClockRule, ClockState, clock_states
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.compliance.models import Framework, Incident, IncidentUpdate
from atesta_api.modules.compliance.scoring import active_frameworks
from atesta_api.modules.compliance.text import filled
from atesta_api.modules.evidence.api import record_attestation
from atesta_api.modules.identity.api import Member, Role, person, require_member, require_role
from atesta_api.platform.audit import record
from atesta_api.platform.db import DbSession
from atesta_api.platform.i18n import Locale, message

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["compliance"])

INCIDENT_CONTROL = "ctl.incident_response"
CLOCK_SKEW = timedelta(minutes=5)

type UpdateKind = Literal["note", "clock", "closed"]


def _error(status: int, code: str) -> HTTPException:
    return HTTPException(status, detail={"code": code})


@dataclass(frozen=True, slots=True)
class ClockDef:
    rule: ClockRule
    framework_key: str
    framework_name: str
    requirement: str
    title_es: str
    title_en: str


def clock_defs(session: Session) -> list[ClockDef]:
    """Reporting clocks of the active packs, keyed `<framework>:<clock>`."""
    keys = [f.key for f in active_frameworks(session)]
    rows = session.execute(
        select(Framework.key, Framework.name, Framework.attributes)
        .where(Framework.key.in_(keys))
        .order_by(Framework.key)
    )
    out: list[ClockDef] = []
    for key, name, attributes in rows.tuples():
        for clock in attributes.get("reporting_clocks", []):
            after = clock.get("after")
            rule = ClockRule(
                ref=f"{key}:{clock['key']}",
                hours=clock.get("hours"),
                months=clock.get("months"),
                after=f"{key}:{after}" if after else None,
                needs=clock["needs"],
            )
            out.append(
                ClockDef(
                    rule, key, name, clock["requirement"], clock["title_es"], clock["title_en"]
                )
            )
    return out


class IncidentIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    aware_at: datetime
    significant: bool
    personal_data: bool

    @field_validator("title")
    @classmethod
    def tidy(cls, value: str) -> str:
        return filled(value)

    @field_validator("aware_at")
    @classmethod
    def known_and_past(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("the time needs a time zone")
        if value > datetime.now(UTC) + CLOCK_SKEW:
            raise ValueError("the time is in the future")
        return value


class UpdateIn(BaseModel):
    kind: UpdateKind
    clock: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def clock_for_clocks(self) -> "UpdateIn":
        if (self.kind == "clock") != (self.clock is not None):
            raise ValueError("a clock update names its clock, and only it does")
        if self.kind == "note" and not self.note.strip():
            raise ValueError("a note needs text")
        return self


class ClockOut(BaseModel):
    ref: str
    framework_key: str
    framework_name: str
    requirement: str
    title_es: str
    title_en: str
    state: Literal["met", "running", "overdue", "waiting"]
    due_at: datetime | None
    met_at: datetime | None
    late: bool


class UpdateOut(BaseModel):
    kind: UpdateKind
    clock: str | None
    note: str
    recorded_at: datetime


class IncidentSummary(BaseModel):
    id: uuid.UUID
    title: str
    aware_at: datetime
    significant: bool
    personal_data: bool
    created_at: datetime
    closed_at: datetime | None
    next_due_at: datetime | None
    overdue: int


class IncidentOut(IncidentSummary):
    clocks: list[ClockOut]
    updates: list[UpdateOut]


def _updates(session: Session, org: uuid.UUID, ids: Sequence[uuid.UUID]) -> list[IncidentUpdate]:
    return list(
        session.scalars(
            select(IncidentUpdate)
            .where(IncidentUpdate.organization_id == org, IncidentUpdate.incident_id.in_(ids))
            .order_by(IncidentUpdate.recorded_at, IncidentUpdate.id)
        )
    )


def _clocks(
    incident: Incident, updates: list[IncidentUpdate], defs: list[ClockDef]
) -> list[ClockOut]:
    met = {u.clock_ref: u.recorded_at for u in updates if u.clock_ref is not None}
    states: dict[str, ClockState] = {
        s.ref: s
        for s in clock_states(
            [d.rule for d in defs],
            aware_at=incident.aware_at,
            significant=incident.significant,
            personal_data=incident.personal_data,
            met=met,
            now=datetime.now(UTC),
        )
    }
    return [
        ClockOut(
            ref=d.rule.ref,
            framework_key=d.framework_key,
            framework_name=d.framework_name,
            requirement=d.requirement,
            title_es=d.title_es,
            title_en=d.title_en,
            state=s.state,
            due_at=s.due_at,
            met_at=s.met_at,
            late=s.late,
        )
        for d in defs
        if (s := states.get(d.rule.ref)) is not None
    ]


def _out(incident: Incident, updates: list[IncidentUpdate], defs: list[ClockDef]) -> IncidentOut:
    clocks = _clocks(incident, updates, defs)
    closed = next((u.recorded_at for u in updates if u.kind == "closed"), None)
    pending = [c.due_at for c in clocks if c.state in ("running", "overdue") and c.due_at]
    return IncidentOut(
        id=incident.id,
        title=incident.title,
        aware_at=incident.aware_at,
        significant=incident.significant,
        personal_data=incident.personal_data,
        created_at=incident.created_at,
        closed_at=closed,
        next_due_at=None if closed else min(pending, default=None),
        overdue=0 if closed else sum(c.state == "overdue" for c in clocks),
        clocks=clocks,
        updates=[
            UpdateOut(
                kind=cast(UpdateKind, u.kind),
                clock=u.clock_ref,
                note=u.note,
                recorded_at=u.recorded_at,
            )
            for u in updates
        ],
    )


def _incident(session: Session, org: uuid.UUID, incident_id: uuid.UUID) -> Incident:
    row = session.scalar(
        select(Incident).where(Incident.organization_id == org, Incident.id == incident_id)
    )
    if row is None:
        raise _error(404, "compliance.incident_not_found")
    return row


def open_incidents(session: Session, org: uuid.UUID) -> list[IncidentOut]:
    """Open incidents with their clocks, for "Ahora"."""
    incidents = list(session.scalars(select(Incident).where(Incident.organization_id == org)))
    updates = _updates(session, org, [i.id for i in incidents])
    defs = clock_defs(session)
    out = [_out(i, [u for u in updates if u.incident_id == i.id], defs) for i in incidents]
    return [o for o in out if o.closed_at is None]


@router.post("/incidents", status_code=201)
def create_incident(
    body: IncidentIn,
    member: Annotated[Member, Depends(require_role(Role.MEMBER))],
    session: DbSession,
) -> IncidentOut:
    incident = Incident(
        organization_id=member.organization_id,
        title=body.title,
        aware_at=body.aware_at,
        significant=body.significant,
        personal_data=body.personal_data,
        created_by=member.user_id,
    )
    session.add(incident)
    session.flush()
    session.refresh(incident)
    record(
        session,
        organization_id=member.organization_id,
        action="incident.created",
        target_type="incident",
        target_id=str(incident.id),
        actor_user_id=member.user_id,
        metadata={"significant": body.significant, "personal_data": body.personal_data},
    )
    return _out(incident, [], clock_defs(session))


@router.get("/incidents")
def list_incidents(
    member: Annotated[Member, Depends(require_member)], session: DbSession
) -> list[IncidentSummary]:
    org = member.organization_id
    incidents = list(
        session.scalars(
            select(Incident)
            .where(Incident.organization_id == org)
            .order_by(Incident.aware_at.desc(), Incident.id)
        )
    )
    updates = _updates(session, org, [i.id for i in incidents])
    defs = clock_defs(session)
    return [
        IncidentSummary(
            **_out(i, [u for u in updates if u.incident_id == i.id], defs).model_dump(
                exclude={"clocks", "updates"}
            )
        )
        for i in incidents
    ]


@router.get("/incidents/{incident_id}")
def read_incident(
    incident_id: uuid.UUID, member: Annotated[Member, Depends(require_member)], session: DbSession
) -> IncidentOut:
    org = member.organization_id
    incident = _incident(session, org, incident_id)
    return _out(incident, _updates(session, org, [incident_id]), clock_defs(session))


def _closing_statement(
    lang: Locale, incident: Incident, clocks: list[ClockOut], at: datetime, email: str
) -> str:
    parts = [
        message(lang, "routines.incident_closed").format(
            title=incident.title,
            aware=incident.aware_at.isoformat(timespec="minutes"),
            date=at.isoformat(timespec="minutes"),
            email=email,
        )
    ]
    for clock in clocks:
        title = clock.title_en if lang == "en" else clock.title_es
        if clock.met_at is None:
            parts.append(
                message(lang, "routines.incident_clock_open").format(
                    clock=title, framework=clock.framework_name
                )
            )
            continue
        timing = message(
            lang, "routines.incident_late" if clock.late else "routines.incident_on_time"
        )
        parts.append(
            message(lang, "routines.incident_clock_met").format(
                clock=title,
                framework=clock.framework_name,
                at=clock.met_at.isoformat(timespec="minutes"),
                timing=timing,
            )
        )
    return " ".join(parts)


@router.post("/incidents/{incident_id}/updates", status_code=201)
def add_update(
    incident_id: uuid.UUID,
    body: UpdateIn,
    member: Annotated[Member, Depends(require_role(Role.MEMBER))],
    session: DbSession,
) -> IncidentOut:
    org = member.organization_id
    incident = _incident(session, org, incident_id)
    defs = clock_defs(session)
    before = _out(incident, _updates(session, org, [incident_id]), defs)
    if before.closed_at is not None:
        raise _error(409, "compliance.incident_closed")
    if body.kind == "clock":
        clock = next((c for c in before.clocks if c.ref == body.clock), None)
        if clock is None:
            raise _error(422, "compliance.clock_unknown")
        if clock.state == "met":
            raise _error(409, "compliance.clock_met")
        if clock.state == "waiting":
            raise _error(409, "compliance.clock_waiting")
    update = IncidentUpdate(
        organization_id=org,
        incident_id=incident_id,
        kind=body.kind,
        clock_ref=body.clock,
        note=body.note.strip(),
        recorded_by=member.user_id,
    )
    session.add(update)
    session.flush()
    session.refresh(update)
    after = _out(incident, _updates(session, org, [incident_id]), defs)
    if body.kind == "closed":
        email, locale = person(session, member.user_id)
        lang: Locale = "en" if locale == "en" else "es"
        record_attestation(
            session,
            organization_id=org,
            author=member.user_id,
            control_key=INCIDENT_CONTROL,
            title=message(lang, "routines.incident_title").format(title=incident.title),
            statement=_closing_statement(lang, incident, after.clocks, update.recorded_at, email),
        )
    record(
        session,
        organization_id=org,
        action=f"incident.{'clock_met' if body.kind == 'clock' else body.kind}",
        target_type="incident",
        target_id=str(incident_id),
        actor_user_id=member.user_id,
        metadata={"clock": body.clock} if body.clock else None,
    )
    return after
