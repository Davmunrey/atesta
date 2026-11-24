"""Immediate notices from audit events (notifications spec PR 2; issue 386).

Connections, scanning and the worker's malware results (evidence-malware-scanning spec) call
queue_event in the transaction that records the event, so the job exists only if the event does.
The job reads the event back by id: job arguments hold ids only (ADR-012 amendment 2).
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from atesta_api.modules.identity.api import Role, organization_profile, recipients
from atesta_api.modules.notifications.config import mail_config
from atesta_api.modules.notifications.kinds import Kind
from atesta_api.modules.notifications.send import deliver
from atesta_api.modules.notifications.texts import madrid_day, provider, text
from atesta_api.platform.audit import AuditEvent
from atesta_api.platform.queue import defer

TASK = "notify_event"
QUEUE = "notifications"
CONNECTION_ALERTS = {"connection.revoked": "revoked", "connection.over_privileged": "extra"}
SCAN_PROBLEMS = frozenset({"scan.failed", "scan.blocked"})
EVIDENCE_MALWARE = "evidence.file_malware_found"
NOTIFIABLE = frozenset(CONNECTION_ALERTS) | SCAN_PROBLEMS | {EVIDENCE_MALWARE}
OWNERS_AND_ADMINS = frozenset({Role.OWNER, Role.ADMIN})


def queue_event(
    session: Session, organization_id: uuid.UUID, event_id: uuid.UUID, action: str
) -> None:
    """Defer notify_event for an action that notifies; any other action is ignored."""
    if action in NOTIFIABLE:
        defer(
            session,
            TASK,
            queue=QUEUE,
            organization_id=str(organization_id),
            event_id=str(event_id),
        )


def handle_event(
    session: Session, organization_id: uuid.UUID, event_id: uuid.UUID, *, now: datetime
) -> None:
    """The notify_event job: one notice per owner and admin, at most once."""
    event = session.scalar(
        select(AuditEvent).where(
            AuditEvent.organization_id == organization_id, AuditEvent.id == event_id
        )
    )
    if event is None or event.action not in NOTIFIABLE:
        return
    details = event.details or {}
    profile = organization_profile(session, organization_id)
    locale = profile.locale
    base = f"/app/connections?org={organization_id}"
    if event.action in CONNECTION_ALERTS:
        kind, key = Kind.CONNECTION_ALERT, f"event:{event.id}"
        reason = CONNECTION_ALERTS[event.action]
        link = f"{base}&connection={event.target_id}"
        subject = text(locale, f"connection_alert.{reason}.subject")
        body = text(
            locale,
            f"connection_alert.{reason}.body",
            org=profile.name,
            provider=provider(details.get("provider")),
        )
    elif event.action == EVIDENCE_MALWARE:  # no file name or title: rule 2
        kind, key = Kind.EVIDENCE_MALWARE, f"event:{event.id}"
        link = f"/app/activity?org={organization_id}"
        subject = text(locale, "evidence_malware.subject")
        body = text(locale, "evidence_malware.body", org=profile.name)
    else:
        if details.get("trigger") == "activation":
            return  # the admin is on the connections page, verifying
        connection = str(details.get("connection_id") or event.target_id)
        kind, key = Kind.SCAN_PROBLEM, f"scan:{connection}:{madrid_day(now).isoformat()}"
        link = base
        subject = text(locale, "scan_problem.subject")
        body = text(
            locale,
            "scan_problem.body",
            org=profile.name,
            provider=provider(details.get("provider")),
        )
    url = _url(link)
    for person in recipients(session, organization_id, OWNERS_AND_ADMINS):
        deliver(
            session,
            organization_id,
            person,
            kind,
            key,
            profile=profile,
            subject=subject,
            lines=[body, "", text(locale, "open", url=url)],
            today=madrid_day(now),
        )


def _url(path: str) -> str:
    config = mail_config()
    return (config.web_base_url if config else "") + path
