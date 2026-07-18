import json
import logging
import os
from typing import Any

from confluent_kafka import KafkaException, Producer
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka:9092",
)

_producer = Producer(
    {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "client.id": os.getenv("SERVICE_NAME", "api"),
        "enable.idempotence": True,
        "acks": "all",
    }
)

tracer = trace.get_tracer(__name__)


def _normalize_headers(
    headers: dict[str, Any] | None,
) -> dict[str, str]:
    if not headers:
        return {}

    return {
        str(name): str(value)
        for name, value in headers.items()
        if value is not None
    }


def publish_event(
    topic: str,
    payload: dict[str, Any],
    *,
    key: str | None = None,
    headers: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
) -> None:
    delivery_error: list[Exception] = []

    carrier = _normalize_headers(headers)

    # Restore the trace captured when the outbox event was created.
    parent_context = propagate.extract(carrier)

    with tracer.start_as_current_span(
        f"{topic} publish",
        context=parent_context,
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "kafka",
            "messaging.destination.name": topic,
            "messaging.operation.name": "publish",
            "messaging.kafka.message.key": key or "",
        },
    ) as span:
        # Replace the stored parent trace context with this producer span's
        # context before sending the Kafka message.
        carrier.pop("traceparent", None)
        carrier.pop("tracestate", None)
        propagate.inject(carrier)

        def delivery_report(error, message) -> None:
            if error is not None:
                kafka_error = KafkaException(error)
                delivery_error.append(kafka_error)

                span.record_exception(kafka_error)
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        str(error),
                    )
                )

                logger.error(
                    "kafka_delivery_failed",
                    extra={
                        "topic": topic,
                        "error": str(error),
                    },
                )
                return

            span.set_attribute(
                "messaging.kafka.destination.partition",
                message.partition(),
            )
            span.set_attribute(
                "messaging.kafka.message.offset",
                message.offset(),
            )

            logger.info(
                "kafka_event_delivered",
                extra={
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                },
            )

        encoded_headers = [
            (
                name,
                value.encode("utf-8"),
            )
            for name, value in carrier.items()
        ]

        try:
            _producer.produce(
                topic=topic,
                key=key.encode("utf-8") if key else None,
                value=json.dumps(
                    payload,
                    default=str,
                ).encode("utf-8"),
                headers=encoded_headers,
                callback=delivery_report,
            )

            remaining = _producer.flush(timeout_seconds)

            if remaining > 0:
                raise TimeoutError(
                    f"Kafka did not deliver {remaining} message(s) "
                    f"within {timeout_seconds} seconds."
                )

            if delivery_error:
                raise delivery_error[0]

            span.set_status(Status(StatusCode.OK))

        except Exception as exc:
            span.record_exception(exc)
            span.set_status(
                Status(
                    StatusCode.ERROR,
                    str(exc),
                )
            )
            raise