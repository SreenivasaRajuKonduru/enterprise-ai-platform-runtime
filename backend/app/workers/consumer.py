import json
import logging
import os
import signal
import uuid
from typing import Any
from uuid import UUID

from confluent_kafka import Consumer, KafkaError, KafkaException, Message
from opentelemetry import propagate, trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from backend.app.workers.job_processor import process_job

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "kafka:9092",
)

KAFKA_JOB_TOPIC = os.getenv(
    "KAFKA_JOB_TOPIC",
    "ai-platform.jobs",
)

KAFKA_CONSUMER_GROUP = os.getenv(
    "KAFKA_CONSUMER_GROUP",
    "ai-platform-job-workers",
)

WORKER_ID = (
    f"{os.getenv('SERVICE_NAME', 'worker')}-"
    f"{uuid.uuid4().hex[:8]}"
)


class JobConsumer:
    def __init__(self) -> None:
        self.running = True

        self.consumer = Consumer(
            {
                "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
                "group.id": KAFKA_CONSUMER_GROUP,
                "client.id": WORKER_ID,
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )

    def stop(self, *_args: Any) -> None:
        logger.info(
            "worker_shutdown_requested",
            extra={
                "worker_id": WORKER_ID,
                "topic": KAFKA_JOB_TOPIC,
                "consumer_group": KAFKA_CONSUMER_GROUP,
            },
        )

        self.running = False

    def run(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        logger.info(
            "worker_consumer_initializing",
            extra={
                "worker_id": WORKER_ID,
                "topic": KAFKA_JOB_TOPIC,
                "consumer_group": KAFKA_CONSUMER_GROUP,
                "bootstrap_servers": KAFKA_BOOTSTRAP_SERVERS,
            },
        )

        self.consumer.subscribe([KAFKA_JOB_TOPIC])

        logger.info(
            "worker_started",
            extra={
                "worker_id": WORKER_ID,
                "topic": KAFKA_JOB_TOPIC,
                "consumer_group": KAFKA_CONSUMER_GROUP,
            },
        )

        try:
            while self.running:
                try:
                    message = self.consumer.poll(1.0)

                    if message is None:
                        continue

                    if message.error():
                        if (
                            message.error().code()
                            == KafkaError._PARTITION_EOF
                        ):
                            continue

                        raise KafkaException(message.error())

                    should_commit = self._process_message(message)

                    if should_commit:
                        self.consumer.commit(
                            message=message,
                            asynchronous=False,
                        )

                        logger.info(
                            "kafka_offset_committed",
                            extra={
                                "worker_id": WORKER_ID,
                                "topic": message.topic(),
                                "partition": message.partition(),
                                "offset": message.offset(),
                            },
                        )
                    else:
                        logger.warning(
                            "kafka_offset_not_committed",
                            extra={
                                "worker_id": WORKER_ID,
                                "topic": message.topic(),
                                "partition": message.partition(),
                                "offset": message.offset(),
                            },
                        )

                except KafkaException as exc:
                    logger.exception(
                        "kafka_consumer_error",
                        extra={
                            "worker_id": WORKER_ID,
                            "topic": KAFKA_JOB_TOPIC,
                            "consumer_group": KAFKA_CONSUMER_GROUP,
                            "error": str(exc),
                        },
                    )

                except Exception as exc:
                    logger.exception(
                        "worker_poll_loop_error",
                        extra={
                            "worker_id": WORKER_ID,
                            "topic": KAFKA_JOB_TOPIC,
                            "consumer_group": KAFKA_CONSUMER_GROUP,
                            "error": str(exc),
                        },
                    )

        finally:
            try:
                self.consumer.close()

            except Exception as exc:
                logger.exception(
                    "worker_consumer_close_failed",
                    extra={
                        "worker_id": WORKER_ID,
                        "error": str(exc),
                    },
                )

            logger.info(
                "worker_stopped",
                extra={
                    "worker_id": WORKER_ID,
                    "topic": KAFKA_JOB_TOPIC,
                    "consumer_group": KAFKA_CONSUMER_GROUP,
                },
            )

    @staticmethod
    def _extract_headers(message: Message) -> dict[str, str]:
        headers = message.headers()

        if not headers:
            return {}

        carrier: dict[str, str] = {}

        for key, value in headers:
            if value is None:
                continue

            if isinstance(value, bytes):
                carrier[key] = value.decode("utf-8")
            else:
                carrier[key] = str(value)

        return carrier

    @staticmethod
    def _decode_event(message: Message) -> dict[str, Any] | None:
        raw_value = message.value()

        if raw_value is None:
            logger.warning(
                "empty_kafka_message",
                extra={
                    "worker_id": WORKER_ID,
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                },
            )

            return None

        try:
            decoded_value = raw_value.decode("utf-8")
            event = json.loads(decoded_value)

        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.error(
                "invalid_kafka_message",
                extra={
                    "worker_id": WORKER_ID,
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "error": str(exc),
                },
            )

            return None

        if not isinstance(event, dict):
            logger.warning(
                "unsupported_kafka_event_payload",
                extra={
                    "worker_id": WORKER_ID,
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "payload_type": type(event).__name__,
                },
            )

            return None

        return event

    @staticmethod
    def _parse_job_id(
        event: dict[str, Any],
        message: Message,
    ) -> UUID | None:
        job_id_value = event.get("job_id")

        if not job_id_value:
            logger.warning(
                "non_job_event_skipped",
                extra={
                    "worker_id": WORKER_ID,
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "event_type": event.get("event_type"),
                },
            )

            return None

        try:
            return UUID(str(job_id_value))

        except (ValueError, TypeError, AttributeError):
            logger.error(
                "invalid_job_id",
                extra={
                    "worker_id": WORKER_ID,
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "job_id": str(job_id_value),
                },
            )

            return None

    def _process_message(self, message: Message) -> bool:
        event = self._decode_event(message)

        if event is None:
            # Invalid or unsupported messages are committed so they do not
            # block the partition indefinitely.
            return True

        job_id = self._parse_job_id(event, message)

        if job_id is None:
            return True

        try:
            carrier = self._extract_headers(message)

        except UnicodeDecodeError as exc:
            logger.warning(
                "invalid_kafka_headers",
                extra={
                    "worker_id": WORKER_ID,
                    "job_id": str(job_id),
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "error": str(exc),
                },
            )

            carrier = {}

        parent_context = propagate.extract(carrier)

        # Event metadata is stored in Kafka headers.
        # Fall back to the payload for backward compatibility.
        event_id = carrier.get("event_id") or event.get("event_id")

        event_type = (
            carrier.get("event_type")
            or event.get("event_type")
            or "UNKNOWN"
        )

        request_id = (
            carrier.get("request_id")
            or event.get("request_id")
        )

        correlation_id = (
            carrier.get("correlation_id")
            or event.get("correlation_id")
        )

        span_attributes: dict[str, str | int | bool] = {
            "messaging.system": "kafka",
            "messaging.destination.name": message.topic(),
            "messaging.operation.name": "process",
            "messaging.kafka.consumer.group": KAFKA_CONSUMER_GROUP,
            "messaging.kafka.partition": message.partition(),
            "messaging.kafka.offset": message.offset(),
            "job.id": str(job_id),
            "worker.id": WORKER_ID,
            "event.type": str(event_type),
        }

        if event_id:
            span_attributes["event.id"] = str(event_id)

        if request_id:
            span_attributes["request.id"] = str(request_id)

        if correlation_id:
            span_attributes["correlation.id"] = str(
                correlation_id
            )

        with tracer.start_as_current_span(
            f"{message.topic()} process",
            context=parent_context,
            kind=SpanKind.CONSUMER,
            attributes=span_attributes,
        ) as span:
            span_context = span.get_span_context()

            trace_id = format(
                span_context.trace_id,
                "032x",
            )

            span_id = format(
                span_context.span_id,
                "016x",
            )

            logger.info(
                "job_event_received",
                extra={
                    "worker_id": WORKER_ID,
                    "job_id": str(job_id),
                    "event_id": (
                        str(event_id)
                        if event_id
                        else None
                    ),
                    "event_type": str(event_type),
                    "request_id": (
                        str(request_id)
                        if request_id
                        else None
                    ),
                    "correlation_id": (
                        str(correlation_id)
                        if correlation_id
                        else None
                    ),
                    "topic": message.topic(),
                    "partition": message.partition(),
                    "offset": message.offset(),
                    "trace_id": trace_id,
                    "span_id": span_id,
                },
            )

            try:
                result = process_job(
                    job_id=job_id,
                    worker_id=WORKER_ID,
                )

                processed_successfully = bool(result)

                span.set_attribute(
                    "messaging.message.processed",
                    processed_successfully,
                )

                if processed_successfully:
                    span.set_status(
                        Status(StatusCode.OK)
                    )

                    logger.info(
                        "job_event_processed",
                        extra={
                            "worker_id": WORKER_ID,
                            "job_id": str(job_id),
                            "event_id": (
                                str(event_id)
                                if event_id
                                else None
                            ),
                            "event_type": str(event_type),
                            "topic": message.topic(),
                            "partition": message.partition(),
                            "offset": message.offset(),
                            "trace_id": trace_id,
                            "span_id": span_id,
                        },
                    )

                    return True

                error_message = (
                    "Job processing did not complete successfully"
                )

                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        error_message,
                    )
                )

                logger.warning(
                    "job_event_processing_incomplete",
                    extra={
                        "worker_id": WORKER_ID,
                        "job_id": str(job_id),
                        "event_id": (
                            str(event_id)
                            if event_id
                            else None
                        ),
                        "event_type": str(event_type),
                        "topic": message.topic(),
                        "partition": message.partition(),
                        "offset": message.offset(),
                        "trace_id": trace_id,
                        "span_id": span_id,
                    },
                )

                # Do not commit the Kafka offset when processing did not
                # complete successfully.
                return False

            except Exception as exc:
                span.record_exception(
                    exc,
                    attributes={
                        "job.id": str(job_id),
                        "worker.id": WORKER_ID,
                    },
                )

                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        str(exc),
                    )
                )

                logger.exception(
                    "job_event_processing_failed",
                    extra={
                        "worker_id": WORKER_ID,
                        "job_id": str(job_id),
                        "event_id": (
                            str(event_id)
                            if event_id
                            else None
                        ),
                        "event_type": str(event_type),
                        "topic": message.topic(),
                        "partition": message.partition(),
                        "offset": message.offset(),
                        "trace_id": trace_id,
                        "span_id": span_id,
                        "error": str(exc),
                    },
                )

                # Do not commit the Kafka offset. The event can be retried
                # according to the platform's retry and failure policy.
                return False