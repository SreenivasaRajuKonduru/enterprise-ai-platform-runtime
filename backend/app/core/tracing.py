import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor


def configure_tracing():
    service_name = os.getenv("SERVICE_NAME", "api")

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "enterprise-ai-platform",
        }
    )

    provider = TracerProvider(resource=resource)
    processor = SimpleSpanProcessor(ConsoleSpanExporter())

    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)