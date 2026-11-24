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


# Security email nobody can turn off (owner, 2026-11-23).
CRITICAL = frozenset({Kind.CONNECTION_ALERT, Kind.EVIDENCE_MALWARE, Kind.INCIDENT_CLOCK})
OPTIONAL = frozenset(set(Kind) - CRITICAL)


def receivable(role: Role) -> tuple[Kind, ...]:
    """The types a role receives, in display order; auditors receive none."""
    if role in (Role.OWNER, Role.ADMIN):
        return tuple(Kind)
    if role == Role.MEMBER:
        return (Kind.DUE_DIGEST,)  # only the due items of their own measures
    return ()
