"""The external auditor's access window (rbac spec): an end date from tomorrow to a year ahead."""

from datetime import UTC, date, datetime, time, timedelta

from atesta_api.modules.identity.models import Role

MAX_DAYS = 365


def check_end_date(role: Role, end: date | None) -> None:
    """Auditors need an end date in the window; every other role must not carry one."""
    if role != Role.AUDITOR:
        if end is not None:
            raise ValueError("only an auditor has an access end date")
        return
    if end is None:
        raise ValueError("an auditor needs an access end date")
    today = datetime.now(UTC).date()
    if not today < end <= today + timedelta(days=MAX_DAYS):
        raise ValueError("the access end date must be from tomorrow to a year ahead")


def end_of(end: date | None) -> datetime | None:
    """Access lasts through the whole end date (UTC)."""
    return None if end is None else datetime.combine(end, time.max, UTC)


def end_date(expires_at: datetime | None) -> date | None:
    """The end date shown to people, read back from the stored end of day."""
    return None if expires_at is None else expires_at.astimezone(UTC).date()
