"""auth key expiry and budget reservations

Additive only: two nullable columns, no data changes, no locks beyond a brief ALTER.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("request_logs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "budget_reservation",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("request_logs", schema=None) as batch_op:
        batch_op.drop_column("budget_reservation")
    with op.batch_alter_table("api_keys", schema=None) as batch_op:
        batch_op.drop_column("expires_at")
