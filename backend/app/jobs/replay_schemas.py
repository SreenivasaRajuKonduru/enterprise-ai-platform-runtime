from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.jobs.enums import JobStatus


class ReplayJobRequest(BaseModel):
    reason: str = Field(
        min_length=5,
        max_length=1000,
    )

    replay_idempotency_key: str = Field(
        min_length=8,
        max_length=248,
    )


class ReplayJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    replay_id: UUID
    original_job_id: UUID
    replayed_job_id: UUID
    replay_idempotency_key: str
    requested_by: str
    reason: str
    request_id: str
    correlation_id: str
    status: JobStatus
    created_at: datetime


class JobReplayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_job_id: UUID
    replayed_job_id: UUID
    replay_idempotency_key: str
    requested_by: str
    reason: str
    request_id: str
    correlation_id: str
    created_at: datetime


class JobReplayListResponse(BaseModel):
    items: list[JobReplayResponse]
    total: int