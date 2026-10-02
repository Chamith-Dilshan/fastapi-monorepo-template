"""Tracing and error-reporting setup.

Two independent, separately gated pieces:

- OpenTelemetry: exports spans over OTLP. Off by default (`OTEL_ENABLED`)
  so local dev doesn't need a collector running. Per
  `BACKEND_DEVELOPMENT_PLAN.md` Section 9/`AGENT_GUIDE.md` Section 4, every
  agent/LLM call built in the next phase must show up here too — that's
  future `extraction`/`agents` package work, not this module; this module
  only establishes the tracer provider and the FastAPI/SQLAlchemy
  auto-instrumentation every request already benefits from.
- Sentry: hosted, per `BACKEND_DEVELOPMENT_PLAN.md` Section 15 (self-hosting
  Sentry was evaluated and rejected as disproportionate operational load for
  this stage). Off unless `SENTRY_DSN` is set and never enabled in local
  dev even if a DSN is present, so local exceptions don't get reported.
"""

import structlog

from app.core.config import settings

logger = structlog.get_logger("app.observability")


def configure_sentry() -> None:
    if not settings.SENTRY_DSN or settings.is_local:
        return

    import sentry_sdk

    sentry_sdk.init(
        dsn=str(settings.SENTRY_DSN),
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        enable_tracing=True,
        # Traces are inexpensive to sample down; errors are always sent.
        traces_sample_rate=0.1,
    )
    logger.info("sentry_configured", environment=settings.ENVIRONMENT)


def configure_opentelemetry(app: object) -> None:
    if not settings.OTEL_ENABLED:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME as OTEL_SERVICE_NAME
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create(
        {
            OTEL_SERVICE_NAME: settings.SERVICE_NAME,
            "deployment.environment": settings.ENVIRONMENT,
            "service.version": settings.APP_VERSION,
        }
    )
    provider = TracerProvider(resource=resource)

    if settings.OTEL_EXPORTER_OTLP_ENDPOINT:
        exporter = OTLPSpanExporter(endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    else:
        logger.warning(
            "otel_enabled_without_endpoint",
            hint="OTEL_ENABLED=true but OTEL_EXPORTER_OTLP_ENDPOINT is unset; "
            "spans are generated but not exported.",
        )

    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    SQLAlchemyInstrumentor().instrument()
    # Injects trace_id/span_id into the LogRecord; structlog's foreign_pre_chain
    # (app.core.logging) picks these up on every stdlib-originated record.
    LoggingInstrumentor().instrument(set_logging_format=False)

    logger.info(
        "opentelemetry_configured",
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
    )
