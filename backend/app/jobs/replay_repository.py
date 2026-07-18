from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.jobs.replay_models import JobReplay


class ReplayRepository:
    def create(
        self,
        db: Session,
        replay: JobReplay,
    ) -> JobReplay:
        db.add(replay)
        db.flush()
        return replay

    def get_by_id(
        self,
        db: Session,
        replay_id: UUID,
    ) -> JobReplay | None:
        statement = select(JobReplay).where(
            JobReplay.id == replay_id,
        )

        return db.scalar(statement)

    def get_by_idempotency_key(
        self,
        db: Session,
        replay_idempotency_key: str,
    ) -> JobReplay | None:
        statement = select(JobReplay).where(
            JobReplay.replay_idempotency_key
            == replay_idempotency_key,
        )

        return db.scalar(statement)

    def get_by_replayed_job_id(
        self,
        db: Session,
        replayed_job_id: UUID,
    ) -> JobReplay | None:
        statement = select(JobReplay).where(
            JobReplay.replayed_job_id == replayed_job_id,
        )

        return db.scalar(statement)

    def list_for_original_job(
        self,
        db: Session,
        original_job_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[JobReplay]:
        statement = (
            select(JobReplay)
            .where(
                JobReplay.original_job_id
                == original_job_id,
            )
            .order_by(JobReplay.created_at.desc())
            .offset(offset)
            .limit(limit)
        )

        return list(db.scalars(statement))

    def count_for_original_job(
        self,
        db: Session,
        original_job_id: UUID,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(JobReplay)
            .where(
                JobReplay.original_job_id
                == original_job_id,
            )
        )

        return db.scalar(statement) or 0