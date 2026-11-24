"""Notifications foundation, no database (notifications spec, PR 1; #379).

Unsubscribe tokens, message composition and the mailers.
"""

import email
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest
from atesta_api.modules.notifications.api import (
    CRITICAL,
    OPTIONAL,
    FileMailer,
    Kind,
    MemoryMailer,
    TokenError,
    UnsubscribeLinks,
    UnsubscribeTokens,
    compose,
)

KEY = bytes(range(32))
ORG, USER = uuid.uuid4(), uuid.uuid4()
TODAY = date(2026, 11, 23)
LINKS = UnsubscribeLinks.for_token("https://app.example.com/", "abc")


def tokens(key: bytes = KEY) -> UnsubscribeTokens:
    return UnsubscribeTokens(key)


def test_kinds_split_into_critical_and_optional() -> None:
    assert {Kind.CONNECTION_ALERT, Kind.EVIDENCE_MALWARE, Kind.INCIDENT_CLOCK} == CRITICAL
    assert {Kind.SCAN_PROBLEM, Kind.DUE_DIGEST, Kind.WEEKLY_SUMMARY} == OPTIONAL


def test_a_token_opens_to_what_it_sealed_and_hides_it() -> None:
    token = tokens().issue(ORG, USER, Kind.DUE_DIGEST, today=TODAY)
    assert str(ORG) not in token and str(USER) not in token and "due_digest" not in token
    opened = tokens().open(token, today=TODAY + timedelta(days=60))
    assert (opened.organization_id, opened.user_id, opened.kind) == (ORG, USER, Kind.DUE_DIGEST)


@pytest.mark.parametrize(
    "bad",
    [
        lambda t: t[:-2] + ("A" if t[-2] != "A" else "B") + t[-1],  # tampered
        lambda t: tokens(bytes(32)).issue(ORG, USER, Kind.DUE_DIGEST, today=TODAY),  # other key
        lambda t: "",
        lambda t: "not-base64!",
    ],
)
def test_a_forged_or_damaged_token_is_refused(bad: object) -> None:
    token = tokens().issue(ORG, USER, Kind.DUE_DIGEST, today=TODAY)
    with pytest.raises(TokenError):
        tokens().open(bad(token), today=TODAY)  # type: ignore[operator]


def test_a_token_expires_after_sixty_days() -> None:
    token = tokens().issue(ORG, USER, Kind.WEEKLY_SUMMARY, today=TODAY)
    with pytest.raises(TokenError):
        tokens().open(token, today=TODAY + timedelta(days=61))


def test_no_token_is_ever_issued_for_a_critical_type() -> None:
    for kind in CRITICAL:
        with pytest.raises(ValueError, match="critical"):
            tokens().issue(ORG, USER, kind, today=TODAY)


def test_the_key_must_be_32_bytes() -> None:
    with pytest.raises(ValueError):
        UnsubscribeTokens(b"short")


def test_an_optional_message_carries_one_click_unsubscribe() -> None:
    message = compose(
        to="ana@example.com",
        sender="Atesta <avisos@example.com>",
        kind=Kind.DUE_DIGEST,
        locale="es",
        subject="Vencimientos próximos",
        lines=["Política de copias: revisión el 23 dic 2026"],
        unsubscribe=LINKS,
    )
    assert message.headers["List-Unsubscribe"] == (
        "<https://app.example.com/api/v1/unsubscribe?token=abc>"
    )
    assert message.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    # A person's click is a GET to the web page, which asks before acting (never the API).
    assert "https://app.example.com/unsubscribe#token=abc" in message.body  # never sent to a server
    assert "/api/v1/unsubscribe" not in message.body
    assert "Política de copias" in message.body


def test_a_critical_message_has_no_unsubscribe_and_says_why() -> None:
    for locale in ("es", "en"):
        message = compose(
            to="ana@example.com",
            sender="Atesta <avisos@example.com>",
            kind=Kind.CONNECTION_ALERT,
            locale=locale,
            subject="x",
            lines=["y"],
            unsubscribe=None,
        )
        assert "List-Unsubscribe" not in message.headers
        assert "unsubscribe" not in message.body.lower()
    with pytest.raises(ValueError):
        compose(
            to="a@example.com",
            sender="s@example.com",
            kind=Kind.DUE_DIGEST,
            locale="es",
            subject="x",
            lines=[],
            unsubscribe=None,  # an optional type must offer the way out
        )


def test_the_body_is_plain_text_so_a_title_cannot_inject_markup() -> None:
    message = compose(
        to="ana@example.com",
        sender="s@example.com",
        kind=Kind.SCAN_PROBLEM,
        locale="en",
        subject="Scan failed",
        lines=['<a href="https://evil.example">Policy</a>'],
        unsubscribe=LINKS,
    )
    raw = message.as_bytes()
    parsed = email.message_from_bytes(raw)
    assert parsed.get_content_type() == "text/plain"
    assert parsed["To"] == "ana@example.com" and parsed["Subject"] == "Scan failed"


def test_a_header_injection_in_the_subject_is_refused() -> None:
    with pytest.raises(ValueError):
        compose(
            to="ana@example.com",
            sender="s@example.com",
            kind=Kind.SCAN_PROBLEM,
            locale="en",
            subject="Hello\r\nBcc: victim@example.com",
            lines=[],
            unsubscribe=LINKS,
        )


def test_the_file_mailer_writes_one_eml_per_message(tmp_path: Path) -> None:
    mailer = FileMailer(tmp_path)
    message = compose(
        to="ana@example.com",
        sender="s@example.com",
        kind=Kind.WEEKLY_SUMMARY,
        locale="es",
        subject="Resumen semanal",
        lines=["Hola"],
        unsubscribe=LINKS,
    )
    message_id = mailer.send(message)
    files = list(tmp_path.glob("*.eml"))
    assert len(files) == 1 and message_id in files[0].name
    assert email.message_from_bytes(files[0].read_bytes())["Subject"] == "Resumen semanal"


def test_the_memory_mailer_keeps_what_it_sent() -> None:
    mailer = MemoryMailer()
    message = compose(
        to="ana@example.com",
        sender="s@example.com",
        kind=Kind.INCIDENT_CLOCK,
        locale="en",
        subject="Clock",
        lines=["Due"],
        unsubscribe=None,
    )
    assert mailer.send(message) and mailer.sent == [message]
