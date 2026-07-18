from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.jobs.enums import JobStatus
from backend.app.jobs.models import Job
from backend.app.outbox.models import OutboxEvent


class JobRepository:
    def get_by_id(
        self,
        db: Session,
        job_id: UUID,
    ) -> Job | None:
        statement = select(Job).where(
            Job.id == job_id,
        )
        return db.scalar(statement)
    
    def get_by_id_for_update(
        self,
        db: Session,
        job_id: UUID,
    ) -> Job | None:
        statement = (
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
        )

        return db.scalar(statement)

    def get_by_idempotency_key(
        self,
        db: Session,
        idempotency_key: str,
    ) -> Job | None:
        statement = select(Job).where(
            Job.idempotency_key == idempotency_key,
        )
        return db.scalar(statement)

    def create(
        self,
        db: Session,
        job: Job,
    ) -> Job:
        db.add(job)
        db.flush()
        return job

    def claim_job(
        self,
        db: Session,
        job_id: UUID,
        worker_id: str,
    ) -> Job | None:
        statement = (
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
        )

        job = db.scalar(statement)

        if job is None:
            return None

        claimable_statuses = {
            JobStatus.PENDING.value,
            JobStatus.QUEUED.value,
            JobStatus.RETRYING.value,
        }

        if job.status not in claimable_statuses:
            return None

        now = datetime.now(timezone.utc)

        if job.queued_at is None:
            job.queued_at = now

        job.status = JobStatus.RUNNING.value
        job.claimed_by = worker_id
        job.started_at = now
        job.failed_at = None
        job.error_code = None
        job.error_message = None
        job.next_retry_at = None
        job.version += 1

        db.flush()
        return job

    def mark_completed(
        self,
        db: Session,
        job: Job,
        result: dict[str, Any],
    ) -> None:
        job.status = JobStatus.COMPLETED.value
        job.result = result
        job.completed_at = datetime.now(timezone.utc)
        job.failed_at = None
        job.next_retry_at = None
        job.error_code = None
        job.error_message = None
        job.claimed_by = None
        job.version += 1

        db.flush()

    def mark_failed(
        self,
        db: Session,
        job: Job,
        error_code: str,
        error_message: str,
    ) -> None:
        now = datetime.now(timezone.utc)

        job.error_code = error_code
        job.error_message = error_message[:4000]
        job.failed_at = now
        job.claimed_by = None
        job.version += 1

        if job.retry_count < job.max_retries:
            # retry_count represents retries scheduled/performed,
            # not the initial execution attempt.
            job.retry_count += 1

            delay_seconds = 2 ** job.retry_count

            job.status = JobStatus.RETRYING.value
            job.next_retry_at = (
                now + timedelta(seconds=delay_seconds)
            )

        else:
            job.status = JobStatus.DEAD_LETTERED.value
            job.next_retry_at = None

            # Total attempts include the initial execution plus all retries.
            attempt_count = job.retry_count + 1

            dlq_event = OutboxEvent(
                id=uuid4(),
                aggregate_type="JOB",
                aggregate_id=job.id,
                event_type="JOB_DEAD_LETTERED",
                event_version=1,
                topic="ai-platform.jobs.dlq",
                partition_key=str(job.id),
                payload={
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "payload": job.payload,
                    "error_code": error_code,
                    "error_message": error_message[:4000],
                    "attempt_count": attempt_count,
                    "max_retries": job.max_retries,
                    "request_id": str(job.request_id),
                    "correlation_id": str(job.correlation_id),
                    "failed_at": now.isoformat(),
                },
                headers={
                    "event_id": str(uuid4()),
                    "event_type": "JOB_DEAD_LETTERED",
                    "request_id": str(job.request_id),
                    "correlation_id": str(job.correlation_id),
                },
            )

            db.add(dlq_event)

        db.flush()
    
    def get_retryable_jobs(
        self,
        db: Session,
        limit: int = 100,
    ):
        now = datetime.now(timezone.utc)

        statement = (
            select(Job)
            .where(
                Job.status == JobStatus.RETRYING.value,
                Job.next_retry_at <= now,
            )
            .limit(limit)
        )

        return list(db.scalars(statement))