import os

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


def configure_tracing(app: FastAPI, engine: Engine) -> None:
    service_name = os.getenv("SERVICE_NAME", "ai-platform-api")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "enterprise-ai-platform",
            "deployment.environment": os.getenv(
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

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=provider,
        excluded_urls="health,ready,metrics",
    )

    RequestsInstrumentor().instrument(
        tracer_provider=provider
    )

    SQLAlchemyInstrumentor().instrument(
        engine=engine,
        tracer_provider=provider,
    )