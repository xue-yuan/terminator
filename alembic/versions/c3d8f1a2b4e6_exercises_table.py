"""exercises table: workout items and plan exercises refer to exercises by id

Revision ID: c3d8f1a2b4e6
Revises: a41c7e2d9f03
Create Date: 2026-11-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3d8f1a2b4e6"
down_revision: str | None = "a41c7e2d9f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Names were free text before: trim and cap them the same way everywhere below.
NAME = "left(btrim({}), 100)"

# For each referring table: the tables and condition that lead to the owner,
# and the owner's user id column.
REFERRERS = {
    "workout_items": ("workouts w", "w.id = t.workout_id", "w.user_id"),
    "plan_exercises": ("plan_days d, plans p", "d.id = t.day_id AND p.id = d.plan_id", "p.creator_id"),
}


def upgrade() -> None:
    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("muscle_group", sa.String(20)),
        sa.Column("notes", sa.Text()),
        sa.Column("rep_min", sa.Integer()),
        sa.Column("rep_max", sa.Integer()),
        sa.Column("increment", sa.Float()),
        sa.Column("rest_seconds", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_exercises_user_name", "exercises", ["user_id", sa.text("lower(name)")], unique=True)

    # One exercise per user and name (ignoring case), spelled as most recently logged.
    name = NAME.format("name")
    op.execute(f"""
        INSERT INTO exercises (id, user_id, name)
        SELECT gen_random_uuid(), user_id, name FROM (
            SELECT DISTINCT ON (user_id, lower({name})) user_id, {name} AS name
            FROM (
                SELECT w.user_id, i.exercise_name AS name, w.performed_at AS at
                FROM workout_items i JOIN workouts w ON w.id = i.workout_id
                UNION ALL
                SELECT p.creator_id, e.exercise_name, '-infinity'::timestamptz
                FROM plan_exercises e
                JOIN plan_days d ON d.id = e.day_id
                JOIN plans p ON p.id = d.plan_id
            ) used
            ORDER BY user_id, lower({name}), at DESC
        ) latest
    """)

    for table, (tables, path, owner) in REFERRERS.items():
        op.add_column(table, sa.Column("exercise_id", sa.Uuid(), nullable=True))
        op.execute(f"""
            UPDATE {table} t SET exercise_id = e.id
            FROM {tables}, exercises e
            WHERE {path} AND e.user_id = {owner}
              AND lower(e.name) = lower({NAME.format("t.exercise_name")})
        """)
        op.alter_column(table, "exercise_id", nullable=False)
        op.create_foreign_key(f"{table}_exercise_id_fkey", table, "exercises", ["exercise_id"], ["id"])
        op.create_index(f"ix_{table}_exercise_id", table, ["exercise_id"])
    op.drop_index("ix_workout_items_exercise_key", table_name="workout_items")
    for table in REFERRERS:
        op.drop_column(table, "exercise_name")


def downgrade() -> None:
    for table in REFERRERS:
        op.add_column(table, sa.Column("exercise_name", sa.String(), nullable=True))
        op.execute(f"UPDATE {table} t SET exercise_name = e.name FROM exercises e WHERE e.id = t.exercise_id")
        op.alter_column(table, "exercise_name", nullable=False)
        op.drop_index(f"ix_{table}_exercise_id", table_name=table)
        op.drop_constraint(f"{table}_exercise_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "exercise_id")
    op.create_index("ix_workout_items_exercise_key", "workout_items", [sa.text("lower(exercise_name)")])
    op.drop_index("uq_exercises_user_name", table_name="exercises")
    op.drop_table("exercises")
