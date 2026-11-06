"""benchmark execution claims

Additive only: one new table with a unique (revision, schedule_day) constraint. No existing table or
data changes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "benchmark_execution_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.String(length=64), nullable=False),
        sa.Column("schedule_day", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_benchmark_execution_claims")),
        sa.UniqueConstraint(
            "revision",
            "schedule_day",
            name=op.f("uq_benchmark_execution_claims_revision_schedule_day"),
        ),
    )


def downgrade() -> None:
    op.drop_table("benchmark_execution_claims")
