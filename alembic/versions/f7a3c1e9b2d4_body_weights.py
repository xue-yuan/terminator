"""body weights

Revision ID: f7a3c1e9b2d4
Revises: e5f2a9c7d1b3
Create Date: 2026-11-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7a3c1e9b2d4"
down_revision: str | None = "e5f2a9c7d1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "body_weights",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("unit IN ('kg', 'lb')", name="body_weights_unit_check"),
    )
    op.create_index("ix_body_weights_user_measured", "body_weights", ["user_id", "measured_at"])


def downgrade() -> None:
    op.drop_index("ix_body_weights_user_measured", table_name="body_weights")
    op.drop_table("body_weights")
