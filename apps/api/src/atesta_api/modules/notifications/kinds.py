"""Notification types and who may receive each (notifications spec, Notification types)."""

from enum import StrEnum

from atesta_api.modules.identity.api import Role


class Kind(StrEnum):
    CONNECTION_ALERT = "connection_alert"
    EVIDENCE_MALWARE = "evidence_malware"
    INCIDENT_CLOCK = "incident_clock"
    SCAN_PROBLEM = "scan_problem"
    DUE_DIGEST = "due_digest"
    WEEKLY_SUMMARY = "weekly_summary"
    SERVICE_NOTICE = "service_notice"  # about the service itself (operator-portal spec)


# Security email nobody can turn off (owner, 2026-11-23).
CRITICAL = frozenset({Kind.CONNECTION_ALERT, Kind.EVIDENCE_MALWARE, Kind.INCIDENT_CLOCK})
# Service notices (suspended, reactivated, export requested, closure started by Atesta) are never
# a preference: nobody can turn them off, and they reach a suspended organization.
SERVICE = frozenset({Kind.SERVICE_NOTICE})
OPTIONAL = frozenset(set(Kind) - CRITICAL - SERVICE)


def receivable(role: Role) -> tuple[Kind, ...]:
    """The types a role receives, in display order; auditors receive none."""
    if role in (Role.OWNER, Role.ADMIN):
        return tuple(k for k in Kind if k not in SERVICE)
    if role == Role.MEMBER:
        return (Kind.DUE_DIGEST,)  # only the due items of their own measures
    return ()
