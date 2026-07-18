from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.outbox.enums import OutboxStatus
from backend.app.outbox.models import OutboxEvent


class OutboxRepository:
    def create(
        self,
        db: Session,
        event: OutboxEvent,
    ) -> OutboxEvent:
        db.add(event)
        db.flush()
        return event

    def claim_batch(
        self,
        db: Session,
        *,
        publisher_id: str,
        batch_size: int = 50,
    ) -> list[OutboxEvent]:
        now = datetime.now(timezone.utc)

        events = (
            db.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == OutboxStatus.PENDING.value,
                    OutboxEvent.next_attempt_at <= now,
                )
                .order_by(OutboxEvent.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for event in events:
            event.status = OutboxStatus.PROCESSING.value
            event.claimed_by = publisher_id
            event.processing_started_at = now

        db.flush()
        return events

    def mark_published(
        self,
        db: Session,
        event: OutboxEvent,
    ) -> None:
        event.status = OutboxStatus.PUBLISHED.value
        event.published_at = datetime.now(timezone.utc)
        event.claimed_by = None
        event.processing_started_at = None
        event.last_error = None

        db.flush()

    def mark_failed(
        self,
        db: Session,
        event: OutboxEvent,
        error: str,
        *,
        max_attempts: int = 10,
    ) -> None:
        event.attempt_count += 1
        event.last_error = error[:5000]
        event.claimed_by = None
        event.processing_started_at = None

        if event.attempt_count >= max_attempts:
            event.status = OutboxStatus.FAILED.value
        else:
            backoff_seconds = min(
                2 ** event.attempt_count,
                300,
            )

            event.status = OutboxStatus.PENDING.value
            event.next_attempt_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=backoff_seconds)
            )

        db.flush()

    def recover_stale_claims(
        self,
        db: Session,
        *,
        stale_after_seconds: int = 300,
    ) -> int:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(seconds=stale_after_seconds)

        events = (
            db.execute(
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == OutboxStatus.PROCESSING.value,
                    OutboxEvent.processing_started_at < stale_before,
                )
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )

        for event in events:
            event.status = OutboxStatus.PENDING.value
            event.claimed_by = None
            event.processing_started_at = None
            event.next_attempt_at = now
            event.last_error = "Recovered stale publisher claim."

        db.flush()
        return len(events)