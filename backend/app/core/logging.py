"""Structured logging configuration.

Replaces the previous bare ``logging.basicConfig`` call with structlog so
every log line — ours and the stdlib/uvicorn logs that pass through it — is
a structured record carrying `request_id` (see `app.core.request_context`)
and, once OpenTelemetry is wired in (`app.core.observability`), `trace_id` /
`span_id` (added automatically by the OTel logging instrumentation). Records
render as JSON everywhere except local dev, where a human-readable console
renderer is easier to read while iterating.

Call `configure_logging()` once, as the very first thing `app.main` does —
before anything else logs — so no log line is emitted through the stdlib's
unconfigured default handler.
"""

import logging
import sys

import structlog

from app.core.config import settings
from app.core.request_context import request_id_var


def _add_request_id(_logger: object, _method_name: str, event_dict: dict) -> dict:
    # First two params are unused but required: structlog calls every
    # processor with this exact (logger, method_name, event_dict) signature.
    request_id = request_id_var.get()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict


def _add_service_context(_logger: object, _method_name: str, event_dict: dict) -> dict:
    # Same structlog processor contract as _add_request_id above.
    event_dict["service"] = settings.SERVICE_NAME
    event_dict["environment"] = settings.ENVIRONMENT
    return event_dict


def configure_logging() -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        _add_service_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.log_json:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        # Foreign (stdlib/uvicorn) log records haven't been through the
        # shared_processors chain above, so re-run the parts that matter
        # (timestamp, request id, service context) before rendering them
        # in the same shape as our own structlog-emitted records.
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Route uvicorn's own loggers through the same handler/formatter instead
    # of letting them keep their default plain-text output.
    for noisy_logger in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "gunicorn.error",
    ):
        logging.getLogger(noisy_logger).handlers = [handler]
        logging.getLogger(noisy_logger).propagate = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
