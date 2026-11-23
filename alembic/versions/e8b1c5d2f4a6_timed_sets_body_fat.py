"""timed and cardio sets, body fat

Revision ID: e8b1c5d2f4a6
Revises: b8c4e7f1a2d6
Create Date: 2026-11-23 00:00:00

- exercises.log_type / catalog_exercises.log_type: what a set of the exercise
  is: weight × reps ("reps"), a time ("time"), or a time and a distance
  ("cardio"). An exercise's own is null until set: the library's counts then.
- workout_sets.duration_seconds / distance_m: what a timed or cardio set logs
  (its reps are 0).
- body_weights.body_fat: percent, optional.

Only adds (nullable columns, or a default everything already is), so it runs
before the backend that uses them is deployed. The library's new cardio
entries come after that backend is live (f3c7a9e1b2d5): an older one can't
read the "cardio" muscle group.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e8b1c5d2f4a6"
down_revision: str | None = "b8c4e7f1a2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("exercises", sa.Column("log_type", sa.String(10), nullable=True))
    op.create_check_constraint("exercises_log_type_check", "exercises", "log_type IN ('reps', 'time', 'cardio')")
    op.add_column(
        "catalog_exercises", sa.Column("log_type", sa.String(10), server_default="reps", nullable=False)
    )
    op.create_check_constraint(
        "catalog_exercises_log_type_check", "catalog_exercises", "log_type IN ('reps', 'time', 'cardio')"
    )
    op.add_column("workout_sets", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column("workout_sets", sa.Column("distance_m", sa.Float(), nullable=True))
    op.add_column("body_weights", sa.Column("body_fat", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("body_weights", "body_fat")
    op.drop_column("workout_sets", "distance_m")
    op.drop_column("workout_sets", "duration_seconds")
    op.drop_constraint("catalog_exercises_log_type_check", "catalog_exercises", type_="check")
    op.drop_column("catalog_exercises", "log_type")
    op.drop_constraint("exercises_log_type_check", "exercises", type_="check")
    op.drop_column("exercises", "log_type")
