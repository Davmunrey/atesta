"""The daily due digest and the Monday weekly summary (notifications spec PR 3; issue 388).

One notify_daily chain per organization, at 08:00 Europe/Madrid. Compliance, scanning and
connections supply the facts through their api.py; the worker composes them. Due notices go at
30, 7 and 1 day before a date, one digest a day; members only see their own assigned measures.
The weekly summary is sent every Monday, even when nothing changed (owner, 2026-11-24).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import Role, organization_profile, recipients
from atesta_api.modules.notifications.config import mail_config
from atesta_api.modules.notifications.kinds import Kind
from atesta_api.modules.notifications.send import deliver
from atesta_api.modules.notifications.texts import MADRID, day, madrid_day, text
from atesta_api.platform.i18n import Locale
from atesta_api.platform.queue import defer

DAILY_TASK = "notify_daily"
QUEUE = "notifications"
SEND_HOUR = 8  # Europe/Madrid
NOTICE_DAYS = (30, 7, 1)
EVERYONE = frozenset({Role.OWNER, Role.ADMIN, Role.MEMBER})

type DueKind = Literal["control_review", "policy_review", "access_review", "assignment"]


@dataclass(frozen=True, slots=True)
class DueItem:
    kind: DueKind
    title_es: str
    title_en: str | None
    due_on: date
    owner_user_id: uuid.UUID | None  # an assignment's owner; None for org-level items
    path: str  # where in the app it is resolved


@dataclass(frozen=True, slots=True)
class WeeklyFacts:
    frameworks: Sequence[tuple[str, float | None]] = field(default_factory=tuple)
    scans: Mapping[str, int] = field(default_factory=dict)
    inactive_connections: int = 0
    due_soon: int = 0
    overdue: int = 0


def notice_days(today: date) -> frozenset[date]:
    return frozenset(today + timedelta(days=d) for d in NOTICE_DAYS)


def next_daily_run(now: datetime) -> datetime:
    """The next 08:00 in Madrid strictly after now, in UTC (summer and winter time alike)."""
    local = now.astimezone(MADRID)
    slot = datetime.combine(local.date(), time(SEND_HOUR), tzinfo=MADRID)
    if slot <= local:
        slot = datetime.combine(local.date() + timedelta(days=1), time(SEND_HOUR), tzinfo=MADRID)
    return slot.astimezone(UTC)


def is_send_slot(now: datetime) -> bool:
    """True inside the 08:00 hour in Madrid; a chain started at another time only re-arms."""
    return now.astimezone(MADRID).hour == SEND_HOUR


def defer_daily(session: Session, organization_id: uuid.UUID, *, now: datetime) -> bool:
    """Defer the next notify_daily; False when one is already waiting (queueing lock)."""
    seconds = max(0, int((next_daily_run(now) - now).total_seconds()))
    try:
        with session.begin_nested():  # a refused insert must not abort the caller's transaction
            defer(
                session,
                DAILY_TASK,
                queue=QUEUE,
                queueing_lock=f"daily:{organization_id}",
                schedule_in_seconds=seconds,
                organization_id=str(organization_id),
            )
    except AlreadyEnqueued:
        return False
    return True


def _url(path: str) -> str:
    config = mail_config()
    return (config.web_base_url if config else "") + path


def _item_line(item: DueItem, locale: Locale) -> str:
    title = item.title_en if locale == "en" and item.title_en else item.title_es
    return text(locale, f"due_digest.{item.kind}", title=title, date=day(item.due_on, locale))


def send_due_digest(
    session: Session, organization_id: uuid.UUID, items: Sequence[DueItem], *, now: datetime
) -> None:
    """One digest per person and day: owners and admins see every item, members their own."""
    if not items:
        return
    profile = organization_profile(session, organization_id)
    locale = profile.locale
    today = madrid_day(now)
    ordered = sorted(items, key=lambda i: (i.due_on, i.kind, i.title_es))
    for person in recipients(session, organization_id, EVERYONE):
        mine = [
            i
            for i in ordered
            if person.role in (Role.OWNER, Role.ADMIN) or i.owner_user_id == person.user_id
        ]
        if not mine:
            continue
        lines = [text(locale, "due_digest.intro", org=profile.name), ""]
        lines += [f"- {_item_line(i, locale)}" for i in mine]
        lines += ["", text(locale, "open", url=_url(f"/app/my-work?org={organization_id}"))]
        deliver(
            session,
            organization_id,
            person,
            Kind.DUE_DIGEST,
            f"digest:{today.isoformat()}",
            profile=profile,
            subject=text(locale, "due_digest.subject", count=str(len(mine))),
            lines=lines,
            today=today,
        )


def _percent(score: float, locale: Locale) -> str:
    rounded = f"{score:.1f}".rstrip("0").rstrip(".")
    return f"{rounded.replace('.', ',')} %" if locale == "es" else f"{rounded}%"


def send_weekly_summary(
    session: Session, organization_id: uuid.UUID, facts: WeeklyFacts, *, now: datetime
) -> None:
    """Owners and admins, once per ISO week; the first Monday of a month links the report."""
    profile = organization_profile(session, organization_id)
    locale = profile.locale
    today = madrid_day(now)
    year, week, _ = today.isocalendar()
    lines = [text(locale, "weekly.intro", org=profile.name), ""]
    quiet = (
        not facts.frameworks
        and not any(facts.scans.values())
        and not (facts.inactive_connections or facts.due_soon or facts.overdue)
    )
    if quiet:
        lines.append(text(locale, "weekly.quiet"))
    for name, score in facts.frameworks:
        result = (
            text(locale, "weekly.unscored")
            if score is None
            else text(locale, "weekly.score", percent=_percent(score, locale))
        )
        lines.append(f"- {name}: {result}")
    if facts.frameworks:
        lines.append(text(locale, "weekly.not_an_assessment"))
    lines.append(
        text(
            locale,
            "weekly.scans",
            ok=str(sum(v for k, v in facts.scans.items() if k in ("succeeded", "partial"))),
            problems=str(sum(v for k, v in facts.scans.items() if k in ("failed", "blocked"))),
        )
    )
    lines.append(text(locale, "weekly.connections", count=str(facts.inactive_connections)))
    lines.append(text(locale, "weekly.due", soon=str(facts.due_soon), overdue=str(facts.overdue)))
    lines += ["", text(locale, "open", url=_url(f"/app/org?org={organization_id}"))]
    if today.day <= 7:  # the first Monday of the month
        lines.append(text(locale, "weekly.report", url=_url(f"/app/report?org={organization_id}")))
    for person in recipients(session, organization_id, frozenset({Role.OWNER, Role.ADMIN})):
        deliver(
            session,
            organization_id,
            person,
            Kind.WEEKLY_SUMMARY,
            f"week:{year}-W{week:02d}",
            profile=profile,
            subject=text(locale, "weekly.subject"),
            lines=lines,
            today=today,
        )
