from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.jobs.enums import JobStatus, JobType


class JobCreateRequest(BaseModel):
    job_type: JobType = JobType.RAG_QUERY
    payload: dict[str, Any]
    idempotency_key: str = Field(
        min_length=1,
        max_length=255,
    )
    correlation_id: str | None = Field(
        default=None,
        max_length=64,
    )
    max_retries: int = Field(
        default=5,
        ge=0,
        le=20,
    )


class JobCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: str
    correlation_id: str
    job_type: JobType
    status: JobStatus
    idempotency_key: str
    created_at: datetime


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    request_id: str
    correlation_id: str
    job_type: JobType
    status: JobStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None
    error_code: str | None
    error_message: str | None
    retry_count: int
    max_retries: int
    idempotency_key: str
    claimed_by: str | None
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    failed_at: datetime | None
    next_retry_at: datetime | None
    version: int
