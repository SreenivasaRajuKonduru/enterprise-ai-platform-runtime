from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.jobs.schemas import (
    JobCreateRequest,
    JobCreateResponse,
    JobResponse,
)
from backend.app.jobs.service import (
    IdempotencyConflictError,
    JobService,
)


router = APIRouter(
    prefix="/jobs",
    tags=["Jobs"],
)

job_service = JobService()


@router.post(
    "",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_job(
    payload: JobCreateRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    request_id = request.state.request_id

    try:
        job, created = job_service.create_job(
            db=db,
            request=payload,
            request_id=request_id,
        )
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    if not created:
        response.status_code = status.HTTP_200_OK

    return job


@router.get(
    "/{job_id}",
    response_model=JobResponse,
)
def get_job(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    job = job_service.get_job(
        db=db,
        job_id=job_id,
    )

    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )

    return job
