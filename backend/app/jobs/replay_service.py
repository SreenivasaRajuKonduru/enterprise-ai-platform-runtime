from uuid import UUID

from opentelemetry import trace
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.jobs.enums import JobStatus, JobType
from backend.app.jobs.models import Job
from backend.app.jobs.replay_models import JobReplay
from backend.app.jobs.replay_repository import ReplayRepository
from backend.app.jobs.replay_schemas import ReplayJobRequest
from backend.app.jobs.repository import JobRepository
from backend.app.jobs.schemas import JobCreateRequest
from backend.app.jobs.service import JobService


tracer = trace.get_tracer(__name__)


class ReplayJobNotFoundError(Exception):
    """Raised when the original job does not exist."""


class JobNotReplayableError(Exception):
    """Raised when the original job is not dead-lettered."""


class ReplayIdempotencyConflictError(Exception):
    """Raised when a replay key belongs to a different original job."""


class ReplayService:
    def __init__(
        self,
        job_repository: JobRepository | None = None,
        replay_repository: ReplayRepository | None = None,
        job_service: JobService | None = None,
    ):
        self.job_repository = job_repository or JobRepository()
        self.replay_repository = (
            replay_repository or ReplayRepository()
        )
        self.job_service = job_service or JobService(
            job_repository=self.job_repository,
        )

    def replay_job(
        self,
        db: Session,
        original_job_id: UUID,
        request: ReplayJobRequest,
        requested_by: str,
        request_id: str,
    ) -> tuple[JobReplay, Job, bool]:
        """
        Replays a dead-lettered job.

        Atomically creates:

        1. A new Job
        2. A JOB_CREATED outbox event
        3. A JobReplay audit record
        """
        try:
            with tracer.start_as_current_span(
                "dlq.replay.request",
            ) as replay_span:
                replay_span.set_attribute(
                    "replay.original_job_id",
                    str(original_job_id),
                )
                replay_span.set_attribute(
                    "replay.requested_by",
                    requested_by,
                )

                existing_replay = (
                    self.replay_repository
                    .get_by_idempotency_key(
                        db=db,
                        replay_idempotency_key=(
                            request.replay_idempotency_key
                        ),
                    )
                )

                if existing_replay:
                    return self._resolve_existing_replay(
                        db=db,
                        existing_replay=existing_replay,
                        original_job_id=original_job_id,
                    )

                original_job = (
                    self.job_repository.get_by_id_for_update(
                        db=db,
                        job_id=original_job_id,
                    )
                )

                if original_job is None:
                    raise ReplayJobNotFoundError(
                        f"Job {original_job_id} was not found."
                    )

                if (
                    original_job.status
                    != JobStatus.DEAD_LETTERED.value
                ):
                    raise JobNotReplayableError(
                        "Only DEAD_LETTERED jobs can be replayed. "
                        f"Current status: {original_job.status}."
                    )

                replay_job_request = self._build_job_request(
                    original_job=original_job,
                    request=request,
                )

                with tracer.start_as_current_span(
                    "dlq.replay.job.create",
                ) as job_span:
                    replayed_job, created = (
                        self.job_service
                        .create_job_without_commit(
                            db=db,
                            request=replay_job_request,
                            request_id=request_id,
                        )
                    )

                    job_span.set_attribute(
                        "replay.replayed_job_id",
                        str(replayed_job.id),
                    )
                    job_span.set_attribute(
                        "replay.job_created",
                        created,
                    )

                if not created:
                    existing_replay = (
                        self.replay_repository
                        .get_by_replayed_job_id(
                            db=db,
                            replayed_job_id=replayed_job.id,
                        )
                    )

                    if existing_replay:
                        return self._resolve_existing_replay(
                            db=db,
                            existing_replay=existing_replay,
                            original_job_id=original_job_id,
                        )

                    raise ReplayIdempotencyConflictError(
                        "A replay job already exists for this "
                        "idempotency key, but its replay audit "
                        "record could not be found."
                    )

                with tracer.start_as_current_span(
                    "dlq.replay.audit.create",
                ) as audit_span:
                    replay = JobReplay(
                        original_job_id=original_job.id,
                        replayed_job_id=replayed_job.id,
                        replay_idempotency_key=(
                            request.replay_idempotency_key
                        ),
                        requested_by=requested_by,
                        reason=request.reason.strip(),
                        request_id=request_id,
                        correlation_id=(
                            replayed_job.correlation_id
                        ),
                    )

                    self.replay_repository.create(
                        db=db,
                        replay=replay,
                    )

                    audit_span.set_attribute(
                        "replay.audit_id",
                        str(replay.id),
                    )

                db.commit()
                db.refresh(replayed_job)
                db.refresh(replay)

                replay_span.set_attribute(
                    "replay.replayed_job_id",
                    str(replayed_job.id),
                )
                replay_span.set_attribute(
                    "replay.audit_id",
                    str(replay.id),
                )

                return replay, replayed_job, True

        except IntegrityError:
            db.rollback()

            existing_replay = (
                self.replay_repository
                .get_by_idempotency_key(
                    db=db,
                    replay_idempotency_key=(
                        request.replay_idempotency_key
                    ),
                )
            )

            if existing_replay:
                return self._resolve_existing_replay(
                    db=db,
                    existing_replay=existing_replay,
                    original_job_id=original_job_id,
                )

            raise

        except Exception:
            db.rollback()
            raise

    def list_replays(
        self,
        db: Session,
        original_job_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[JobReplay], int]:
        original_job = self.job_repository.get_by_id(
            db=db,
            job_id=original_job_id,
        )

        if original_job is None:
            raise ReplayJobNotFoundError(
                f"Job {original_job_id} was not found."
            )

        items = self.replay_repository.list_for_original_job(
            db=db,
            original_job_id=original_job_id,
            limit=limit,
            offset=offset,
        )

        total = self.replay_repository.count_for_original_job(
            db=db,
            original_job_id=original_job_id,
        )

        return items, total

    def _resolve_existing_replay(
        self,
        db: Session,
        existing_replay: JobReplay,
        original_job_id: UUID,
    ) -> tuple[JobReplay, Job, bool]:
        if existing_replay.original_job_id != original_job_id:
            raise ReplayIdempotencyConflictError(
                "The replay idempotency key is already associated "
                "with a different original job."
            )

        replayed_job = self.job_repository.get_by_id(
            db=db,
            job_id=existing_replay.replayed_job_id,
        )

        if replayed_job is None:
            raise ReplayIdempotencyConflictError(
                "The replay audit record exists, but the replayed "
                "job could not be found."
            )

        return existing_replay, replayed_job, False

    @staticmethod
    def _build_job_request(
        original_job: Job,
        request: ReplayJobRequest,
    ) -> JobCreateRequest:
        try:
            job_type = JobType(original_job.job_type)
        except ValueError as exc:
            raise JobNotReplayableError(
                "The original job contains an unsupported job type: "
                f"{original_job.job_type}."
            ) from exc

        return JobCreateRequest(
            job_type=job_type,
            payload=original_job.payload,
            max_retries=original_job.max_retries,
            correlation_id=original_job.correlation_id,
            idempotency_key=(
                "replay:"
                f"{request.replay_idempotency_key}"
            ),
        )