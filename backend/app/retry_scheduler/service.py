from datetime import datetime, timezone
from uuid import uuid4

from backend.app.db.session import SessionLocal
from backend.app.jobs.enums import JobStatus
from backend.app.jobs.repository import JobRepository
from backend.app.outbox.models import OutboxEvent


class RetryScheduler:
    def __init__(self) -> None:
        self.repository = JobRepository()

    def run_once(self) -> None:
        db = SessionLocal()

        try:
            jobs = self.repository.get_retryable_jobs(db)

            for job in jobs:
                scheduled_at = datetime.now(timezone.utc)
                event_id = uuid4()

                # Update the job and create the retry event in the same
                # database transaction.
                job.status = JobStatus.QUEUED.value
                job.next_retry_at = None

                retry_payload = {
                    "job_id": str(job.id),
                    "job_type": job.job_type,
                    "status": JobStatus.QUEUED.value,
                    "retry_count": job.retry_count,
                    "max_retries": job.max_retries,
                    "request_id": str(job.request_id),
                    "correlation_id": str(job.correlation_id),
                    "scheduled_at": scheduled_at.isoformat(),
                }

                retry_headers = {
                    "event_id": str(event_id),
                    "event_type": "JOB_RETRY",
                    "request_id": str(job.request_id),
                    "correlation_id": str(job.correlation_id),
                    "retry_count": job.retry_count,
                }

                outbox_event = OutboxEvent(
                    id=event_id,
                    aggregate_type="JOB",
                    aggregate_id=job.id,
                    event_type="JOB_RETRY",
                    event_version=1,
                    topic="ai-platform.jobs",
                    partition_key=str(job.id),
                    payload=retry_payload,
                    headers=retry_headers,
                )

                db.add(job)
                db.add(outbox_event)

            db.commit()

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()