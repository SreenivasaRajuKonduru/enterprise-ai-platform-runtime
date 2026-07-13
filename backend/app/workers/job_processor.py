import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.jobs.enums import JobType
from backend.app.jobs.repository import JobRepository
from backend.app.workers.handlers.rag_query import handle_rag_query

logger = logging.getLogger(__name__)

repository = JobRepository()


def execute_handler(
    db: Session,
    job_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if job_type == JobType.RAG_QUERY.value:
        return handle_rag_query(
            db=db,
            payload=payload,
        )

    raise ValueError(
        f"Unsupported job type: {job_type}"
    )


def process_job(
    job_id: UUID,
    worker_id: str,
) -> bool:
    db = SessionLocal()

    try:
        job = repository.claim_job(
            db=db,
            job_id=job_id,
            worker_id=worker_id,
        )

        if job is None:
            db.rollback()

            logger.info(
                "job_not_claimed",
                extra={
                    "job_id": str(job_id),
                    "worker_id": worker_id,
                },
            )
            return True

        job_type = job.job_type
        payload = job.payload

        # Persist RUNNING before expensive RAG/LLM execution.
        db.commit()

        try:
            result = execute_handler(
                db=db,
                job_type=job_type,
                payload=payload,
            )

        except Exception as exc:
            db.rollback()

            failed_job = repository.get_by_id(
                db=db,
                job_id=job_id,
            )

            if failed_job is not None:
                repository.mark_failed(
                    db=db,
                    job=failed_job,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                )
                db.commit()

            logger.exception(
                "job_execution_failed",
                extra={
                    "job_id": str(job_id),
                    "worker_id": worker_id,
                    "error": str(exc),
                },
            )
            return True

        completed_job = repository.get_by_id(
            db=db,
            job_id=job_id,
        )

        if completed_job is None:
            db.rollback()
            raise RuntimeError(
                f"Job disappeared during processing: {job_id}"
            )

        repository.mark_completed(
            db=db,
            job=completed_job,
            result=result,
        )

        db.commit()

        logger.info(
            "job_completed",
            extra={
                "job_id": str(job_id),
                "worker_id": worker_id,
            },
        )

        return True

    except Exception as exc:
        db.rollback()

        logger.exception(
            "job_processing_failed",
            extra={
                "job_id": str(job_id),
                "worker_id": worker_id,
                "error": str(exc),
            },
        )

        return False

    finally:
        db.close()
