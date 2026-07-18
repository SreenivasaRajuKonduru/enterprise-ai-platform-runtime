import hashlib
import json
import uuid

from opentelemetry.propagate import inject
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.jobs.enums import JobStatus
from backend.app.jobs.models import Job
from backend.app.jobs.repository import JobRepository
from backend.app.jobs.schemas import JobCreateRequest
from backend.app.outbox.enums import OutboxStatus
from backend.app.outbox.models import OutboxEvent
from backend.app.outbox.repository import OutboxRepository


class IdempotencyConflictError(Exception):
    """Raised when one idempotency key is reused for different payloads."""


class JobService:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        outbox_repository: OutboxRepository | None = None,
    ):
        self.job_repository = job_repository or JobRepository()
        self.outbox_repository = (
            outbox_repository or OutboxRepository()
        )

    def create_job(
        self,
        db: Session,
        request: JobCreateRequest,
        request_id: str,
    ) -> tuple[Job, bool]:
        """
        Public job-creation method.

        Creates the job and transactional outbox event, then commits
        the transaction.
        """
        try:
            job, created = self.create_job_without_commit(
                db=db,
                request=request,
                request_id=request_id,
            )

            if not created:
                return job, False

            db.commit()
            db.refresh(job)

            return job, True

        except IntegrityError:
            db.rollback()

            existing_job = (
                self.job_repository.get_by_idempotency_key(
                    db=db,
                    idempotency_key=request.idempotency_key,
                )
            )

            if existing_job:
                payload_hash = self._calculate_payload_hash(
                    request.payload,
                )

                self._validate_existing_job(
                    existing_job=existing_job,
                    request=request,
                    payload_hash=payload_hash,
                )

                return existing_job, False

            raise

        except Exception:
            db.rollback()
            raise

    def create_job_without_commit(
        self,
        db: Session,
        request: JobCreateRequest,
        request_id: str,
    ) -> tuple[Job, bool]:
        """
        Creates a job and its JOB_CREATED outbox event without committing.

        This method allows callers such as ReplayService to include job
        creation, outbox creation, and audit creation in one transaction.
        """
        payload_hash = self._calculate_payload_hash(
            request.payload,
        )

        existing_job = (
            self.job_repository.get_by_idempotency_key(
                db=db,
                idempotency_key=request.idempotency_key,
            )
        )

        if existing_job:
            self._validate_existing_job(
                existing_job=existing_job,
                request=request,
                payload_hash=payload_hash,
            )

            return existing_job, False

        correlation_id = (
            request.correlation_id or request_id
        )

        job = Job(
            request_id=request_id,
            correlation_id=correlation_id,
            job_type=request.job_type.value,
            status=JobStatus.PENDING.value,
            payload=request.payload,
            payload_hash=payload_hash,
            retry_count=0,
            max_retries=request.max_retries,
            idempotency_key=request.idempotency_key,
            version=1,
        )

        self.job_repository.create(
            db=db,
            job=job,
        )

        trace_headers: dict[str, str] = {}
        inject(trace_headers)

        event = OutboxEvent(
            aggregate_type="JOB",
            aggregate_id=job.id,
            event_type="JOB_CREATED",
            event_version=1,
            topic="ai-platform.jobs",
            partition_key=str(job.id),
            payload={
                "job_id": str(job.id),
                "request_id": job.request_id,
                "correlation_id": job.correlation_id,
                "job_type": job.job_type,
                "status": job.status,
                "payload": job.payload,
                "payload_hash": job.payload_hash,
                "retry_count": job.retry_count,
                "max_retries": job.max_retries,
            },
            headers={
                **trace_headers,
                "event_id": str(uuid.uuid4()),
                "event_type": "JOB_CREATED",
                "correlation_id": job.correlation_id,
                "request_id": job.request_id,
            },
            status=OutboxStatus.PENDING.value,
            attempt_count=0,
        )

        self.outbox_repository.create(
            db=db,
            event=event,
        )

        return job, True

    def get_job(
        self,
        db: Session,
        job_id: uuid.UUID,
    ) -> Job | None:
        return self.job_repository.get_by_id(
            db=db,
            job_id=job_id,
        )

    @staticmethod
    def _validate_existing_job(
        existing_job: Job,
        request: JobCreateRequest,
        payload_hash: str,
    ) -> None:
        same_request = (
            existing_job.payload_hash == payload_hash
            and existing_job.job_type == request.job_type.value
        )

        if not same_request:
            raise IdempotencyConflictError(
                "The idempotency key is already associated "
                "with a different request."
            )

    @staticmethod
    def _calculate_payload_hash(
        payload: dict,
    ) -> str:
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        return hashlib.sha256(
            canonical_payload.encode("utf-8"),
        ).hexdigest()