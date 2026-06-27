import json
import os
import time

import redis
from confluent_kafka import Consumer, Producer, KafkaException

BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

MAIN_TOPIC = "user.registered"
RETRY_TOPIC = "user.registered.retry"
DLQ_TOPIC = "user.registered.dlq"

MAX_RETRIES = 3
IDEMPOTENCY_TTL_SECONDS = 86400

redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

producer = Producer({"bootstrap.servers": BOOTSTRAP_SERVERS})

consumer = Consumer(
    {
        "bootstrap.servers": BOOTSTRAP_SERVERS,
        "group.id": "enterprise-ai-platform-worker",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    }
)


def publish(topic: str, event: dict):
    producer.produce(topic, json.dumps(event).encode("utf-8"))
    producer.flush()


def get_event_id(event: dict) -> str:
    return event.get("event_id") or f"{event.get('event_type')}:{event.get('user_id')}:{event.get('email')}"


def already_processed(event: dict) -> bool:
    event_id = get_event_id(event)
    key = f"idempotency:{event_id}"

    created = redis_client.set(key, "processing", nx=True, ex=IDEMPOTENCY_TTL_SECONDS)

    if not created:
        return True

    return False


def mark_processed(event: dict):
    event_id = get_event_id(event)
    key = f"idempotency:{event_id}"
    redis_client.set(key, "processed", ex=IDEMPOTENCY_TTL_SECONDS)


def process_user_registered(event: dict):
    print("PROCESSING USER REGISTERED EVENT:", event, flush=True)

    if not event.get("email"):
        raise ValueError("Missing email in user registered event")

    print(f"SUCCESS: welcome workflow completed for {event['email']}", flush=True)


def publish_retry_or_dlq(event: dict, error: Exception):
    retry_count = int(event.get("retry_count", 0)) + 1

    event["retry_count"] = retry_count
    event["last_error"] = str(error)

    event_id = get_event_id(event)
    redis_client.delete(f"idempotency:{event_id}")

    if retry_count <= MAX_RETRIES:
        print(f"RETRY {retry_count}/{MAX_RETRIES}:", event, flush=True)
        time.sleep(2)
        publish(RETRY_TOPIC, event)
    else:
        print("SENDING TO DLQ:", event, flush=True)
        publish(DLQ_TOPIC, event)


def run_worker():
    print("Kafka worker started", flush=True)
    print(f"Listening to topics: {MAIN_TOPIC}, {RETRY_TOPIC}", flush=True)

    consumer.subscribe([MAIN_TOPIC, RETRY_TOPIC])

    try:
        while True:
            msg = consumer.poll(1.0)

            if msg is None:
                continue

            if msg.error():
                raise KafkaException(msg.error())

            event = json.loads(msg.value().decode("utf-8"))

            try:
                if already_processed(event):
                    print("DUPLICATE EVENT SKIPPED:", event, flush=True)
                    consumer.commit(msg)
                    continue

                if event.get("event_type") == MAIN_TOPIC:
                    process_user_registered(event)
                    mark_processed(event)
                else:
                    print("UNKNOWN EVENT:", event, flush=True)

                consumer.commit(msg)

            except Exception as exc:
                publish_retry_or_dlq(event, exc)
                consumer.commit(msg)

    finally:
        consumer.close()


if __name__ == "__main__":
    run_worker()
