import uuid

from sqlalchemy import select

from backend.app.db.session import SessionLocal
from backend.app.jobs.enums import JobStatus
from backend.app.jobs.models import Job
from backend.app.jobs.replay_models import JobReplay
from backend.app.jobs.replay_schemas import ReplayJobRequest
from backend.app.jobs.replay_service import ReplayService
from backend.app.outbox.models import OutboxEvent


def main() -> None:
    db = SessionLocal()

    try:
        original_job = db.scalar(
            select(Job)
            .where(
                Job.status == JobStatus.DEAD_LETTERED.value,
            )
            .order_by(Job.created_at.desc())
            .limit(1)
        )

        if original_job is None:
            print(
                "No DEAD_LETTERED job exists.\n"
                "Create or identify a dead-lettered job before "
                "running this test."
            )
            return

        replay_key = f"manual-{uuid.uuid4()}"
        request_id = str(uuid.uuid4())

        replay_request = ReplayJobRequest(
            reason=(
                "Manual replay validation after confirming "
                "the underlying failure was corrected."
            ),
            replay_idempotency_key=replay_key,
        )

        service = ReplayService()

        replay, replayed_job, created = service.replay_job(
            db=db,
            original_job_id=original_job.id,
            request=replay_request,
            requested_by="manual-test-admin",
            request_id=request_id,
        )

        persisted_replay = db.scalar(
            select(JobReplay).where(
                JobReplay.id == replay.id,
            )
        )

        created_event = db.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.aggregate_type == "JOB",
                OutboxEvent.aggregate_id == replayed_job.id,
                OutboxEvent.event_type == "JOB_CREATED",
            )
            .order_by(OutboxEvent.created_at.desc())
            .limit(1)
        )

        assertions = {
            "new replay created": created is True,
            "new job has different ID": (
                replayed_job.id != original_job.id
            ),
            "new job starts as PENDING": (
                replayed_job.status
                == JobStatus.PENDING.value
            ),
            "audit record exists": (
                persisted_replay is not None
            ),
            "audit references original job": (
                persisted_replay is not None
                and persisted_replay.original_job_id
                == original_job.id
            ),
            "audit references replayed job": (
                persisted_replay is not None
                and persisted_replay.replayed_job_id
                == replayed_job.id
            ),
            "JOB_CREATED outbox event exists": (
                created_event is not None
            ),
            "request ID preserved": (
                replayed_job.request_id == request_id
            ),
            "correlation ID preserved": (
                replayed_job.correlation_id
                == original_job.correlation_id
            ),
            "retry count reset": (
                replayed_job.retry_count == 0
            ),
            "payload copied": (
                replayed_job.payload == original_job.payload
            ),
        }

        print("\nDLQ REPLAY TEST")
        print("=" * 72)
        print(f"Original job ID : {original_job.id}")
        print(f"Replayed job ID : {replayed_job.id}")
        print(f"Replay audit ID : {replay.id}")
        print(f"Replay key      : {replay_key}")
        print(f"Created         : {created}")
        print(f"New job status  : {replayed_job.status}")
        print(f"Outbox event ID : {getattr(created_event, 'id', None)}")
        print("=" * 72)

        failed_assertions = []

        for name, passed in assertions.items():
            marker = "PASS" if passed else "FAIL"
            print(f"[{marker}] {name}")

            if not passed:
                failed_assertions.append(name)

        if failed_assertions:
            raise AssertionError(
                "Replay validation failed: "
                + ", ".join(failed_assertions)
            )

        print("\nReplay service validation passed.")

    finally:
        db.close()


if __name__ == "__main__":
    main()
