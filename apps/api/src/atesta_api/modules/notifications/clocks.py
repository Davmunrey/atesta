"""Incident reporting clocks by email (notifications spec PR 2; issue 386).

Milestones are proportional (owner's "Adelante", 2026-11-24). A clock of up to 72 hours: its
start, 6 hours before and when due. A longer one, such as a final report due in a month: its
start, 7 days and 1 day before, and when due. Compliance computes the clocks (atesta_core.clocks)
and schedules the jobs; at run time the job recomputes them, so a clock met or an incident
closed since then sends nothing. Atesta shows due times; whether a notification is owed is the
organization's decision (incidents.py).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import Role, organization_profile, recipients
from atesta_api.modules.notifications.config import mail_config
from atesta_api.modules.notifications.kinds import Kind
from atesta_api.modules.notifications.send import deliver
from atesta_api.modules.notifications.texts import madrid_day, text, when
from atesta_api.platform.queue import defer

TASK = "notify_clock"
QUEUE = "notifications"
SHORT_HOURS = 72
GRACE = timedelta(hours=3)  # a job that runs late still warns, within this window
OWNERS_AND_ADMINS = frozenset({Role.OWNER, Role.ADMIN})


@dataclass(frozen=True, slots=True)
class ClockTiming:
    ref: str
    due_at: datetime | None
    hours: int | None  # None for a clock counted in months


@dataclass(frozen=True, slots=True)
class IncidentClocks:
    """What the clock job needs from one incident, read through compliance.api."""

    @dataclass(frozen=True, slots=True)
    class Clock:
        timing: ClockTiming
        state: str  # running, overdue, met or waiting
        title_es: str
        title_en: str | None
        framework_name: str

    incident_id: uuid.UUID
    title: str
    closed: bool
    clocks: Sequence[Clock] = field(default_factory=tuple)


def due_milestones(timing: ClockTiming) -> dict[str, datetime]:
    if timing.due_at is None:
        return {}
    due = timing.due_at
    if timing.hours is not None and timing.hours <= SHORT_HOURS:
        return {"before_6h": due - timedelta(hours=6), "due": due}
    return {"before_7d": due - timedelta(days=7), "before_1d": due - timedelta(days=1), "due": due}


def notices_due(timing: ClockTiming, *, state: str, now: datetime) -> list[str]:
    """The notices owed now; the delivery log keeps each to once."""
    if state == "overdue":
        return ["due"]
    if state != "running":
        return []
    owed = ["start"]
    for name, moment in due_milestones(timing).items():
        if name != "due" and moment <= now < moment + GRACE:
            owed.append(name)
    return owed


def schedule_clock_notices(
    session: Session,
    organization_id: uuid.UUID,
    incident_id: uuid.UUID,
    timings: Sequence[ClockTiming],
    *,
    now: datetime,
) -> None:
    """One notify_clock job now and one at each future milestone; ids only."""
    moments = {
        moment for timing in timings for moment in due_milestones(timing).values() if moment > now
    }
    org, incident = str(organization_id), str(incident_id)
    defer(session, TASK, queue=QUEUE, organization_id=org, incident_id=incident)
    for moment in sorted(moments):
        seconds = max(0, int((moment - now).total_seconds()))
        defer(
            session,
            TASK,
            queue=QUEUE,
            schedule_in_seconds=seconds,
            organization_id=org,
            incident_id=incident,
        )


def send_clock_notices(
    session: Session, organization_id: uuid.UUID, incident: IncidentClocks, *, now: datetime
) -> None:
    if incident.closed:
        return
    profile = organization_profile(session, organization_id)
    locale = profile.locale
    config = mail_config()
    url = (config.web_base_url if config else "") + (
        f"/app/incident?org={organization_id}&id={incident.incident_id}"
    )
    people = recipients(session, organization_id, OWNERS_AND_ADMINS)
    for clock in incident.clocks:
        for notice in notices_due(clock.timing, state=clock.state, now=now):
            title = clock.title_en if locale == "en" and clock.title_en else clock.title_es
            due = clock.timing.due_at
            lines = [
                text(locale, "incident_clock.incident", org=profile.name, title=incident.title),
                text(
                    locale,
                    "incident_clock.clock",
                    clock=title,
                    framework=clock.framework_name,
                    due=when(due, locale) if due else "",
                ),
                text(locale, f"incident_clock.{notice}"),
                "",
                text(locale, "open", url=url),
            ]
            for person in people:
                deliver(
                    session,
                    organization_id,
                    person,
                    Kind.INCIDENT_CLOCK,
                    f"{incident.incident_id}:{clock.timing.ref}:{notice}",
                    profile=profile,
                    subject=text(locale, "incident_clock.subject"),
                    lines=lines,
                    today=madrid_day(now),
                )
