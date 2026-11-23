"""Log records carry no exception text and no query strings (log-redaction spec, rule 2)."""

import io
import logging
from collections.abc import Iterator

import pytest
from atesta_api.main import create_app
from atesta_api.platform.logs import install_log_redaction

MARKER = "customer-marker-never-logged"  # stands for any secret or customer value


@pytest.fixture
def capture() -> Iterator[tuple[logging.Logger, io.StringIO]]:
    install_log_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("atesta.test.redaction")
    logger.addHandler(handler)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield logger, stream
    logger.removeHandler(handler)


def _fail() -> None:
    try:
        raise KeyError(f"user {MARKER}")
    except KeyError as error:
        raise RuntimeError(f"wrapped {MARKER}") from error


def test_an_exception_keeps_its_frames_and_types_but_not_its_message(
    capture: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = capture
    try:
        _fail()
    except RuntimeError:
        logger.exception("job failed")
    text = stream.getvalue()
    assert MARKER not in text
    assert "job failed" in text
    assert "KeyError" in text and "builtins.RuntimeError" in text
    assert "direct cause" in text and "in _fail" in text


def test_an_exception_given_as_an_argument_is_logged_as_its_type(
    capture: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = capture
    logger.warning("runner raised %s (%s)", ValueError(MARKER), KeyError(MARKER))
    assert stream.getvalue().strip() == "runner raised builtins.ValueError (builtins.KeyError)"


def test_a_record_without_an_exception_is_left_alone(
    capture: tuple[logging.Logger, io.StringIO],
) -> None:
    logger, stream = capture
    logger.info("scan %s exited %d", "ids-only", 3, exc_info=False)
    assert stream.getvalue().strip() == "scan ids-only exited 3"


@pytest.mark.parametrize(
    ("path", "logged"),
    [
        (f"/auth/callback?code={MARKER}&state=abc", "/auth/callback?[query omitted]"),
        (f"/api/v1/orgs/x/search?q={MARKER}", "/api/v1/orgs/x/search?[query omitted]"),
        (f"/x?{MARKER}", "/x?[query omitted]"),
        ("/api/v1/me", "/api/v1/me"),
    ],
)
def test_access_log_lines_drop_the_query_string(path: str, logged: str) -> None:
    install_log_redaction()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    access = logging.getLogger("uvicorn.access")
    access.addHandler(handler)
    previous = access.level
    access.setLevel(logging.INFO)
    try:
        access.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5", "GET", path, "1.1", 302)
    finally:
        access.removeHandler(handler)
        access.setLevel(previous)
    assert stream.getvalue().strip() == f'127.0.0.1:5 - "GET {logged} HTTP/1.1" 302'


def test_installing_twice_wraps_the_factory_once() -> None:
    install_log_redaction()
    factory = logging.getLogRecordFactory()
    install_log_redaction()
    create_app()
    assert logging.getLogRecordFactory() is factory


def test_create_app_installs_the_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logging, "_logRecordFactory", logging.LogRecord)
    create_app()
    record = logging.getLogger("x").makeRecord("x", 40, "f", 1, "m %s", (ValueError(MARKER),), None)
    assert record.getMessage() == "m builtins.ValueError"
