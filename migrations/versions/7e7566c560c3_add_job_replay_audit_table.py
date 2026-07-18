"""add job replay audit table

Revision ID: 7e7566c560c3
Revises: 4c6a16ea12ac
Create Date: 2026-07-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7e7566c560c3"
down_revision: Union[str, None] = "4c6a16ea12ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "job_replays",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "original_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "replayed_job_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "replay_idempotency_key",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=False,
        ),
        sa.Column(
            "request_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "correlation_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(reason)) > 0",
            name="ck_job_replays_reason_not_empty",
        ),
        sa.CheckConstraint(
            "length(trim(requested_by)) > 0",
            name="ck_job_replays_requested_by_not_empty",
        ),
        sa.ForeignKeyConstraint(
            ["original_job_id"],
            ["jobs.id"],
            name="fk_job_replays_original_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["replayed_job_id"],
            ["jobs.id"],
            name="fk_job_replays_replayed_job_id_jobs",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "replay_idempotency_key",
            name="uq_job_replays_replay_idempotency_key",
        ),
        sa.UniqueConstraint(
            "replayed_job_id",
            name="uq_job_replays_replayed_job_id",
        ),
    )

    op.create_index(
        "ix_job_replays_original_job_created_at",
        "job_replays",
        ["original_job_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_job_replays_request_id",
        "job_replays",
        ["request_id"],
        unique=False,
    )
    op.create_index(
        "ix_job_replays_correlation_id",
        "job_replays",
        ["correlation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_job_replays_correlation_id",
        table_name="job_replays",
    )
    op.drop_index(
        "ix_job_replays_request_id",
        table_name="job_replays",
    )
    op.drop_index(
        "ix_job_replays_original_job_created_at",
        table_name="job_replays",
    )
    op.drop_table("job_replays")
