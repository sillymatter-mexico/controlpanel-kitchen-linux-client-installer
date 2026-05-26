"""Shared logging configuration for all CPK agent processes.

Call ``configure()`` once at the entry point of each process (main function).
"""

from __future__ import annotations

import logging

# Third-party loggers that are too chatty at INFO level.
_QUIET_LOGGERS = (
    "alembic",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "websockets",
    "httpx",
    "httpcore",
)

_FORMAT = "%(asctime)s [%(levelname)s] %(shortname)s: %(message)s"
_DATEFMT = "%H:%M:%S"


class _ShortNameFormatter(logging.Formatter):
    """Like the default formatter, but replaces ``%(name)s`` with the last
    dotted segment of the logger name so the output stays compact.

    Example: ``services.agent.listener`` → ``listener``
    """

    def format(self, record: logging.LogRecord) -> str:
        record.shortname = record.name.rsplit(".", 1)[-1]
        return super().format(record)


def configure(level: int = logging.INFO) -> None:
    """Configure the root logger for a CPK agent process.

    Sets a consistent format, attaches a stream handler to the root logger,
    and silences noisy third-party libraries.

    Args:
        level: Root logging level. Defaults to ``logging.INFO``.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_ShortNameFormatter(fmt=_FORMAT, datefmt=_DATEFMT))

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
