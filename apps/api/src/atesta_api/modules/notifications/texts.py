"""Words and dates of a notice, in the organization's language (i18n-complete spec)."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from atesta_api.platform.i18n import Locale, message

MADRID = ZoneInfo("Europe/Madrid")
_MONTHS: dict[Locale, tuple[str, ...]] = {
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
PROVIDERS = {"m365": "Microsoft 365", "google_workspace": "Google Workspace"}


def madrid_day(moment: datetime) -> date:
    return moment.astimezone(MADRID).date()


def when(moment: datetime, locale: Locale) -> str:
    """A date and time in Madrid: "25 nov 2026, 13:00" or "Nov 25, 2026, 13:00"."""
    local = moment.astimezone(MADRID)
    month = _MONTHS[locale][local.month - 1]
    clock = f"{local.hour:02d}:{local.minute:02d}"
    if locale == "es":
        return f"{local.day} {month} {local.year}, {clock}"
    return f"{month} {local.day}, {local.year}, {clock}"


def day(value: date, locale: Locale) -> str:
    """A date alone: "23 dic 2026" or "Dec 23, 2026"."""
    month = _MONTHS[locale][value.month - 1]
    return (
        f"{value.day} {month} {value.year}"
        if locale == "es"
        else f"{month} {value.day}, {value.year}"
    )


def text(locale: Locale, key: str, **values: str) -> str:
    return message(locale, f"notifications.{key}").format(**values)


def provider(name: object) -> str:
    return PROVIDERS.get(str(name), str(name))
