"""community: high-fives and a community title slot

Revision ID: a3d9c7e5b1f2
Revises: f3c7a9e1b2d5
Create Date: 2026-11-23 12:00:00

high_fives: someone high-fived a finished workout in the community feed.
users.community_title: the community title worn next to the name, apart from
the regular one. Community titles themselves are rows of achievement_unlocks
like any other tier. Only adds, so it runs before the backend that uses it.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3d9c7e5b1f2"
down_revision: str | None = "f3c7a9e1b2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("community_title", sa.String(60), nullable=True))
    op.create_table(
        "high_fives",
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workouts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_high_fives_user_id", "high_fives", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_high_fives_user_id", table_name="high_fives")
    op.drop_table("high_fives")
    op.drop_column("users", "community_title")
