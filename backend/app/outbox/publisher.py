import logging
import os
import time
import uuid

#from backend.app.db.session import SessionLocal
from backend.app.events.producer import publish_event
from backend.app.outbox.repository import OutboxRepository

from backend.app.core.logging import configure_logging
from backend.app.db.session import SessionLocal, engine
from backend.app.observability.tracing import configure_tracing


logger = logging.getLogger(__name__)

PUBLISHER_ID = (
    f"{os.getenv('SERVICE_NAME', 'publisher')}-"
    f"{uuid.uuid4().hex[:8]}"
)

repository = OutboxRepository()


def publish_batch() -> int:
    db = SessionLocal()

    try:
        events = repository.claim_batch(
            db,
            publisher_id=PUBLISHER_ID,
            batch_size=50,
        )

        if not events:
            db.commit()
            return 0

        for event in events:
            try:
                publish_event(
                    topic=event.topic,
                    key=event.partition_key,
                    payload=event.payload,
                    headers=event.headers,
                )

                repository.mark_published(
                    db,
                    event,
                )

            except Exception as exc:
                repository.mark_failed(
                    db,
                    event,
                    str(exc),
                )

        db.commit()

        return len(events)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def run_forever() -> None:
    logger.info(
        "outbox_publisher_started",
        extra={
            "publisher_id": PUBLISHER_ID,
        },
    )

    while True:
        try:
            count = publish_batch()

            if count == 0:
                time.sleep(2)

        except Exception as exc:
            logger.exception(
                "outbox_publisher_failed",
                extra={
                    "error": str(exc),
                },
            )

            time.sleep(5)

def main() -> None:
    configure_logging()

    configure_tracing(
        engine=engine,
    )

    run_forever()

if __name__ == "__main__":
    main()