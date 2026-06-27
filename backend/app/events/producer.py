import json
import logging
import os
from typing import Any

from confluent_kafka import Producer

logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")

_producer = Producer(
    {
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "client.id": os.getenv("SERVICE_NAME", "api"),
    }
)


def _delivery_report(error, message):
    if error is not None:
        logger.error("kafka_delivery_failed", extra={"topic": message.topic(), "error": str(error)})
    else:
        logger.info("kafka_event_delivered", extra={"topic": message.topic()})


def publish_event(topic: str, payload: dict[str, Any]) -> None:
    try:
        _producer.produce(
            topic=topic,
            value=json.dumps(payload).encode("utf-8"),
            callback=_delivery_report,
        )
        _producer.poll(0)
    except Exception as exc:
        logger.error("kafka_publish_failed", extra={"topic": topic, "error": str(exc)})