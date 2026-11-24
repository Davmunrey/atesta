"""The worker's own events reach stdout as bare lines (issue 452).

Without a handler, Python writes only WARNING and above through its last-resort handler, so the
INFO `scan.finished` events the failure-rate alert counts were dropped.
"""

import io
import json
import logging
from collections.abc import Iterator

import pytest
from atesta_api.platform.logs import install_log_redaction
from atesta_worker.jobs import _report
from atesta_worker.logs import configure_logging


@pytest.fixture
def stream() -> Iterator[io.StringIO]:
    out = io.StringIO()
    logger = logging.getLogger("atesta")
    before, level = list(logger.handlers), logger.level
    yield out
    logger.handlers[:] = before
    logger.setLevel(level)


def test_scan_finished_reaches_the_stream_as_exactly_its_json_line(stream: io.StringIO) -> None:
    configure_logging(stream)
    event = {"event": "scan.finished", "status": "failed", "scan_id": "s", "attempts": 3}
    _report(event)
    assert stream.getvalue() == json.dumps(event, sort_keys=True) + "\n"


def test_configuring_twice_adds_no_second_handler(stream: io.StringIO) -> None:
    configure_logging(stream)
    configure_logging(stream)
    logging.getLogger("atesta.file_scans").info("one line")
    assert stream.getvalue() == "one line\n"


def test_debug_records_stay_out(stream: io.StringIO) -> None:
    configure_logging(stream)
    logging.getLogger("atesta.scan").debug("not this")
    assert stream.getvalue() == ""


def test_redaction_still_drops_exception_messages(stream: io.StringIO) -> None:
    install_log_redaction()
    configure_logging(stream)
    try:  # built at run time: the kept traceback frames quote this source line
        raise ValueError("row value " + str(40 + 2))
    except ValueError:
        logging.getLogger("atesta.scan").exception("ingest failed")
    assert "ingest failed" in stream.getvalue()
    assert "row value 42" not in stream.getvalue()


def test_the_worker_entrypoint_configures_logging_before_anything_else(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import atesta_worker.__main__ as entry  # noqa: PLC0415 - patched per test

    calls: list[str] = []
    monkeypatch.setattr(entry, "configure_logging", lambda: calls.append("logs"))
    monkeypatch.delenv("ATESTA_DATABASE_URL", raising=False)
    with pytest.raises(KeyError):
        entry.main()
    assert calls == ["logs"]
