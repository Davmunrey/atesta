"""Plain-text messages and the mailers (notifications spec, PR 1).

Plain text only: a title the customer typed cannot inject markup. Optional types carry RFC 8058
one-click unsubscribe headers. Nothing here logs an address, a subject or a body (rule 2).
"""

import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode

from atesta_api.modules.notifications.kinds import CRITICAL, Kind
from atesta_api.platform.i18n import Locale, message


@dataclass(frozen=True, slots=True)
class Message:
    to: str
    sender: str
    subject: str
    body: str
    headers: dict[str, str] = field(default_factory=dict)

    def as_bytes(self) -> bytes:
        mail = EmailMessage()
        mail["From"], mail["To"], mail["Subject"] = self.sender, self.to, self.subject
        for name, value in self.headers.items():
            mail[name] = value
        mail.set_content(self.body, subtype="plain", charset="utf-8")
        return mail.as_bytes()


@dataclass(frozen=True, slots=True)
class UnsubscribeLinks:
    """Where one token leads: the API for RFC 8058 one-click, the web page for a person."""

    one_click: str  # List-Unsubscribe: POST only, from the mail provider
    page: str  # the link in the body: a GET that explains and asks before acting

    @classmethod
    def for_token(cls, web_base_url: str, token: str) -> "UnsubscribeLinks":
        base = web_base_url.rstrip("/")
        query = urlencode({"token": token})
        # The page reads its token from the fragment, which browsers never send to a server.
        return cls(
            one_click=f"{base}/api/v1/unsubscribe?{query}", page=f"{base}/unsubscribe#{query}"
        )


def _one_line(value: str, what: str) -> str:
    if any(c in value for c in "\r\n\x00"):
        raise ValueError(f"{what} must be a single line")
    return value


def compose(  # noqa: PLR0913 - one call site per notification type, each field named
    *,
    to: str,
    sender: str,
    kind: Kind,
    locale: Locale,
    subject: str,
    lines: list[str],
    unsubscribe: UnsubscribeLinks | None,
) -> Message:
    """A message in the recipient's language; optional types must offer the way out."""
    if kind not in CRITICAL and unsubscribe is None:
        raise ValueError(f"{kind} is optional and needs an unsubscribe link")
    headers: dict[str, str] = {}
    footer = [message(locale, "notifications.footer.why")]
    if unsubscribe is not None and kind not in CRITICAL:
        one_click = _one_line(unsubscribe.one_click, "the one-click URL")
        headers["List-Unsubscribe"] = f"<{one_click}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        page = _one_line(unsubscribe.page, "the unsubscribe page")
        footer.append(message(locale, "notifications.footer.optional").format(url=page))
    else:
        footer.append(message(locale, "notifications.footer.critical"))
    body = "\n".join([*lines, "", "--", *footer]) + "\n"
    return Message(
        to=_one_line(to, "the recipient"),
        sender=_one_line(sender, "the sender"),
        subject=_one_line(subject, "the subject"),
        body=body,
        headers=headers,
    )


class Mailer(Protocol):
    def send(self, message: Message) -> str:
        """Send one message; return the provider's message id."""
        ...


class FileMailer:
    """Local development: one .eml per message under a directory (ATESTA_MAIL_DIR)."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def send(self, message: Message) -> str:
        message_id = uuid.uuid4().hex
        self._directory.mkdir(parents=True, exist_ok=True)
        (self._directory / f"{message_id}.eml").write_bytes(message.as_bytes())
        return message_id


class MemoryMailer:
    """Tests: keeps every message it was given."""

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def send(self, message: Message) -> str:
        self.sent.append(message)
        return f"memory-{len(self.sent)}"
