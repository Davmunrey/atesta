"""Log records carry no exception text and no query strings (log-redaction spec, rule 2).

The process-wide record factory is wrapped, so every logger and handler gets redacted records,
whatever the logging configuration. An exception keeps its frames, type names, SQLSTATE and
schema identifiers. Its message is dropped: PostgreSQL's DETAIL line carries row values.
"""

import logging
import traceback
from collections.abc import Callable, Mapping
from typing import Any

_ACCESS_LOGGER = "uvicorn.access"
_DIAG_FIELDS = (
    ("constraint_name", "constraint"),
    ("table_name", "table"),
    ("column_name", "column"),
)


def _type_name(error: BaseException) -> str:
    kind = type(error)
    return f"{kind.__module__}.{kind.__qualname__}"


def _describe(error: BaseException) -> str:
    """Type name plus psycopg's SQLSTATE and schema identifiers, never the message."""
    parts: list[str] = []
    sqlstate = getattr(error, "sqlstate", None)
    if isinstance(sqlstate, str):
        parts.append(f"sqlstate {sqlstate}")
    diag = getattr(error, "diag", None)
    for attribute, label in _DIAG_FIELDS:
        value = getattr(diag, attribute, None)
        if isinstance(value, str):
            parts.append(f"{label} {value}")
    return _type_name(error) + (f" ({', '.join(parts)})" if parts else "")


def safe_traceback(error: BaseException) -> str:
    """The traceback Python would print, with every exception message removed."""
    chain: list[tuple[BaseException, str | None]] = []
    current: BaseException | None = error
    link: str | None = None
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append((current, link))
        if current.__cause__ is not None:
            current, link = current.__cause__, "direct cause"
        elif current.__context__ is not None and not current.__suppress_context__:
            current, link = current.__context__, "context"
        else:
            current = None
    lines: list[str] = []
    for index, (item, _) in enumerate(reversed(chain)):
        if index:
            joining = chain[len(chain) - index][1]
            lines.append(
                "\nThe above exception was the direct cause of the following exception:\n"
                if joining == "direct cause"
                else "\nDuring handling of the above exception, another exception occurred:\n"
            )
        if item.__traceback__ is not None:
            lines.append("Traceback (most recent call last):")
            lines.extend(f.rstrip("\n") for f in traceback.format_tb(item.__traceback__))
        lines.append(_describe(item))
    return "\n".join(lines)


def _safe_arg(value: object) -> object:
    return _type_name(value) if isinstance(value, BaseException) else value


def strip_query(path: str) -> str:
    """Drop the whole query string: a value, or a bare name, can be a code or a token."""
    base, mark, _ = path.partition("?")
    return f"{base}?[query omitted]" if mark else path


def redact(record: logging.LogRecord) -> logging.LogRecord:
    if record.exc_info:
        error = record.exc_info[1]
        record.exc_text = None if error is None else safe_traceback(error)
        record.exc_info = None
    if isinstance(record.msg, BaseException):
        record.msg = _type_name(record.msg)
    if isinstance(record.args, tuple):
        args = [_safe_arg(arg) for arg in record.args]
        if record.name == _ACCESS_LOGGER and len(args) >= 3 and isinstance(args[2], str):
            args[2] = strip_query(args[2])  # uvicorn: client, method, path, version, status
        record.args = tuple(args)
    elif isinstance(record.args, Mapping):
        record.args = {key: _safe_arg(value) for key, value in record.args.items()}
    return record


class _RedactingFactory:
    def __init__(self, base: Callable[..., logging.LogRecord]) -> None:
        self.base = base

    def __call__(self, *args: Any, **kwargs: Any) -> logging.LogRecord:
        return redact(self.base(*args, **kwargs))


def install_log_redaction() -> None:
    """Wrap the record factory once per process; installing again changes nothing."""
    current = logging.getLogRecordFactory()
    if not isinstance(current, _RedactingFactory):
        logging.setLogRecordFactory(_RedactingFactory(current))
