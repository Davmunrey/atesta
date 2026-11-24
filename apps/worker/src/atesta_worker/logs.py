"""Where the worker's own log lines go (issue 452).

Every `atesta.*` record at INFO and above is written to stdout as its message alone, one line per
record. A JSON event such as `scan.finished` is then the whole line, which CloudWatch JSON metric
filters read (the scan failure-rate alert). Redaction (log-redaction spec) happens when the
record is made, so this handler only ever sees redacted records.
"""

import logging
import sys
from typing import TextIO

_HANDLER = "atesta-worker-stdout"


def configure_logging(stream: TextIO | None = None) -> logging.Handler:
    """Attach the stdout handler to the `atesta` logger once; a second call changes nothing."""
    logger = logging.getLogger("atesta")
    logger.setLevel(logging.INFO)
    for handler in logger.handlers:
        if handler.name == _HANDLER:
            return handler
    handler = logging.StreamHandler(sys.stdout if stream is None else stream)
    handler.name = _HANDLER
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return handler
