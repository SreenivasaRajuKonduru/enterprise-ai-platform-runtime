import logging
import os
from threading import Lock

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_tracing_lock = Lock()
_tracing_initialized = False
_requests_instrumented = False
_sqlalchemy_instrumented = False


def configure_tracing(
    *,
    service_name: str | None = None,
    app: FastAPI | None = None,
    engine: Engine | None = None,
) -> TracerProvider:
    """
    Configure OpenTelemetry for API and background services.

    Safe to call once per process. Background processes such as workers,
    outbox publishers and retry schedulers do not require a FastAPI app.
    """

    global _tracing_initialized
    global _requests_instrumented
    global _sqlalchemy_instrumented

    resolved_service_name = service_name or os.getenv(
        "SERVICE_NAME",
        "enterprise-ai-platform",
    )

    with _tracing_lock:
        current_provider = trace.get_tracer_provider()

        if not _tracing_initialized:
            resource = Resource.create(
                {
                    "service.name": resolved_service_name,
                    "service.namespace": "enterprise-ai-platform",
                    "deployment.environment.name": os.getenv(
                        "ENVIRONMENT",
                        "local",
                    ),
                }
            )

            provider = TracerProvider(resource=resource)

            exporter = OTLPSpanExporter(
                endpoint=os.getenv(
                    "OTEL_EXPORTER_OTLP_ENDPOINT",
                    "http://otel-collector:4317",
                ),
                insecure=True,
            )

            provider.add_span_processor(
                BatchSpanProcessor(exporter)
            )

            trace.set_tracer_provider(provider)

            _tracing_initialized = True

            logger.info(
                "tracing_initialized",
                extra={
                    "service_name": resolved_service_name,
                    "exporter_endpoint": os.getenv(
                        "OTEL_EXPORTER_OTLP_ENDPOINT",
                        "http://otel-collector:4317",
                    ),
                },
            )

        provider = trace.get_tracer_provider()

        if not isinstance(provider, TracerProvider):
            raise RuntimeError(
                "OpenTelemetry TracerProvider was not initialized correctly"
            )

        if not _requests_instrumented:
            RequestsInstrumentor().instrument(
                tracer_provider=provider,
            )
            _requests_instrumented = True

        if engine is not None and not _sqlalchemy_instrumented:
            SQLAlchemyInstrumentor().instrument(
                engine=engine,
                tracer_provider=provider,
            )
            _sqlalchemy_instrumented = True

        if app is not None:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=provider,
                excluded_urls=(
                    "health,ready,metrics"
                ),
            )

        return provider