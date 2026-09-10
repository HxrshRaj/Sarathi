"""Structured JSON logging with correlation ids and a secret denylist.

Never logs credential-shaped keys or raw context bodies (see THREAT_MODEL T4).
"""

from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import IO, Any

import structlog

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_DENYLIST = {
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "api_key",
    "anthropic_api_key",
    "secret",
    "session_secret",
    "encryption_key",
    "cookie",
    "set-cookie",
    "x-csrf-token",
    "client_secret",
}


def _redact(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict.keys()):
        if key.lower() in _DENYLIST:
            event_dict[key] = "«redacted»"
    return event_dict


def _add_correlation_id(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    cid = correlation_id_var.get()
    if cid:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def configure_logging(
    level: str = "INFO", *, json_output: bool = True, stream: IO[str] | None = None
) -> None:
    """Configure structlog + stdlib logging.

    `stream` defaults to stdout. The MCP stdio server passes stderr so log lines
    never corrupt the JSON-RPC stream on stdout.
    """
    stream = stream or sys.stdout
    logging.basicConfig(format="%(message)s", stream=stream, level=level.upper(), force=True)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_correlation_id,
        _redact,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_output
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level.upper())),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "sarathi") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[return-value]
