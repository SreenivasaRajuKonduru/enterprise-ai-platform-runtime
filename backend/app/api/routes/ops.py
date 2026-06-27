from fastapi import APIRouter
from confluent_kafka import Consumer
import json
import os

router = APIRouter(prefix="/ops", tags=["Operations"])

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


@router.get("/dlq")
def get_dlq_messages(limit: int = 10):
    consumer = Consumer(
        {
            "bootstrap.servers": BOOTSTRAP_SERVERS,
            "group.id": "dlq-inspector",
            "auto.offset.reset": "earliest",
        }
    )

    consumer.subscribe(["user.registered.dlq"])

    messages = []

    try:
        while len(messages) < limit:
            msg = consumer.poll(1.0)

            if msg is None:
                break

            if msg.error():
                continue

            messages.append(json.loads(msg.value().decode("utf-8")))

    finally:
        consumer.close()

    return {
        "count": len(messages),
        "messages": messages,
    }
