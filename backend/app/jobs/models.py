import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.jobs.enums import JobStatus, JobType


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            name="uq_jobs_idempotency_key",
        ),
        CheckConstraint(
            "retry_count >= 0",
            name="ck_jobs_retry_count_non_negative",
        ),
        CheckConstraint(
            "max_retries >= 0",
            name="ck_jobs_max_retries_non_negative",
        ),
        CheckConstraint(
            "retry_count <= max_retries",
            name="ck_jobs_retry_count_within_limit",
        ),
        Index(
            "ix_jobs_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "ix_jobs_next_retry_at",
            "next_retry_at",
            postgresql_where=(
                "status = 'RETRYING'"
            ),
        ),
        Index(
            "ix_jobs_request_id",
            "request_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    request_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    correlation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    job_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=JobType.RAG_QUERY.value,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=JobStatus.PENDING.value,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    payload_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )

    idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    claimed_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    queued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )