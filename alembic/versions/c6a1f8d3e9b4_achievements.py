"""achievements: XP per workout, unlocked tiers, the title shown

Revision ID: c6a1f8d3e9b4
Revises: e1f3b5c7a9d2
Create Date: 2026-11-19 00:00:00

Filled in by GET /progress from the workout history the first time it's read,
so no data migration is needed. It only adds (tables and a nullable column), so
it runs before the backend that uses them is deployed, and before the muscle
split after it (b8c4e7f1a2d6), which needs that backend live first.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c6a1f8d3e9b4"
down_revision: str | None = "e1f3b5c7a9d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "xp_awards",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("workout_id", sa.Uuid(), primary_key=True),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "achievement_unlocks",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("achievement", sa.String(40), primary_key=True),
        sa.Column("target", sa.Float(), primary_key=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workout_id", sa.Uuid(), nullable=True),
    )
    op.add_column("users", sa.Column("title", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "title")
    op.drop_table("achievement_unlocks")
    op.drop_table("xp_awards")
