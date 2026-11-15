"""weight units, supersets, per-exercise indexes

Revision ID: a41c7e2d9f03
Revises: 7f3a2c9e41b5
Create Date: 2026-11-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a41c7e2d9f03"
down_revision: str | None = "7f3a2c9e41b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Everything logged so far was entered in kg.
    op.add_column(
        "workout_items",
        sa.Column("weight_unit", sa.String(length=2), nullable=False, server_default="kg"),
    )
    op.create_check_constraint(
        "workout_items_weight_unit_check", "workout_items", "weight_unit IN ('kg', 'lb')"
    )
    op.add_column("workout_items", sa.Column("superset", sa.Integer(), nullable=True))
    op.add_column("plan_exercises", sa.Column("superset", sa.Integer(), nullable=True))

    op.create_index(
        "ix_workout_items_exercise_key", "workout_items", [sa.text("lower(exercise_name)")]
    )
    op.create_index("ix_workout_items_workout_id", "workout_items", ["workout_id"])
    op.create_index("ix_workout_sets_item_id", "workout_sets", ["item_id"])


def downgrade() -> None:
    op.drop_index("ix_workout_sets_item_id", table_name="workout_sets")
    op.drop_index("ix_workout_items_workout_id", table_name="workout_items")
    op.drop_index("ix_workout_items_exercise_key", table_name="workout_items")
    op.drop_column("plan_exercises", "superset")
    op.drop_column("workout_items", "superset")
    op.drop_constraint("workout_items_weight_unit_check", "workout_items", type_="check")
    op.drop_column("workout_items", "weight_unit")
