import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class JobReplay(Base):
    __tablename__ = "job_replays"

    __table_args__ = (
        UniqueConstraint(
            "replayed_job_id",
            name="uq_job_replays_replayed_job_id",
        ),
        UniqueConstraint(
            "replay_idempotency_key",
            name="uq_job_replays_replay_idempotency_key",
        ),
        CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_job_replays_reason_not_empty",
        ),
        CheckConstraint(
            "length(trim(requested_by)) > 0",
            name="ck_job_replays_requested_by_not_empty",
        ),
        Index(
            "ix_job_replays_original_job_created_at",
            "original_job_id",
            "created_at",
        ),
        Index(
            "ix_job_replays_request_id",
            "request_id",
        ),
        Index(
            "ix_job_replays_correlation_id",
            "correlation_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    original_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "jobs.id",
            name="fk_job_replays_original_job_id_jobs",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    replayed_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "jobs.id",
            name="fk_job_replays_replayed_job_id_jobs",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    replay_idempotency_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    requested_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    request_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    correlation_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )