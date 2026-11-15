"""warm-up sets: workout_sets.kind

Revision ID: e5f2a9c7d1b3
Revises: c3d8f1a2b4e6
Create Date: 2026-11-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f2a9c7d1b3"
down_revision: str | None = "c3d8f1a2b4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Everything logged so far counts as a working set.
    op.add_column(
        "workout_sets",
        sa.Column("kind", sa.String(length=10), nullable=False, server_default="working"),
    )
    op.create_check_constraint("workout_sets_kind_check", "workout_sets", "kind IN ('working', 'warmup')")


def downgrade() -> None:
    op.drop_constraint("workout_sets_kind_check", "workout_sets", type_="check")
    op.drop_column("workout_sets", "kind")
