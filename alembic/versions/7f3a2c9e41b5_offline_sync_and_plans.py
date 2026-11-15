"""offline sync ids, tz-aware timestamps, active plan on user, cascades

Revision ID: 7f3a2c9e41b5
Revises: d8e389a67b80
Create Date: 2026-11-14 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7f3a2c9e41b5"
down_revision: str | None = "d8e389a67b80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (table, column, referred table, constraint name) for FKs that gain ON DELETE CASCADE
CASCADE_FKS = [
    ("plans", "creator_id", "users", "plans_creator_id_fkey"),
    ("plan_days", "plan_id", "plans", "plan_days_plan_id_fkey"),
    ("plan_exercises", "day_id", "plan_days", "plan_exercises_day_id_fkey"),
    ("workouts", "user_id", "users", "workouts_user_id_fkey"),
    ("workout_items", "workout_id", "workouts", "workout_items_workout_id_fkey"),
    ("workout_sets", "item_id", "workout_items", "workout_sets_item_id_fkey"),
]

ORDER_COLUMNS = ["plan_days", "plan_exercises", "workout_items", "workout_sets"]


def _not_null_bool(table: str, column: str, default: bool) -> None:
    op.execute(f"UPDATE {table} SET {column} = {str(default).lower()} WHERE {column} IS NULL")
    op.alter_column(
        table, column, nullable=False, server_default=sa.true() if default else sa.false()
    )


def upgrade() -> None:
    # users: booleans NOT NULL; active plan becomes a column
    _not_null_bool("users", "is_active", True)
    _not_null_bool("users", "is_superuser", False)
    op.add_column("users", sa.Column("active_plan_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "users_active_plan_id_fkey", "users", "plans", ["active_plan_id"], ["id"], ondelete="SET NULL"
    )
    op.execute(
        "UPDATE users u SET active_plan_id = a.plan_id "
        "FROM user_active_plans a WHERE a.user_id = u.id AND a.is_active"
    )
    op.drop_table("user_active_plans")

    _not_null_bool("plans", "is_public", False)

    for table in ORDER_COLUMNS:
        op.execute(f'UPDATE {table} SET "order" = 0 WHERE "order" IS NULL')
        op.alter_column(table, "order", nullable=False, server_default="0")

    for table, column, referred, name in CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, referred, [column], ["id"], ondelete="CASCADE")

    # workouts: naive UTC `date` -> tz-aware `performed_at`
    op.execute("UPDATE workouts SET date = timezone('UTC', now()) WHERE date IS NULL")
    op.alter_column(
        "workouts",
        "date",
        type_=sa.DateTime(timezone=True),
        postgresql_using="date AT TIME ZONE 'UTC'",
        nullable=False,
    )
    op.alter_column("workouts", "date", new_column_name="performed_at")

    op.add_column("workouts", sa.Column("uuid", sa.Uuid(), nullable=True))
    op.execute("UPDATE workouts SET uuid = gen_random_uuid()")
    op.alter_column("workouts", "uuid", nullable=False)
    op.create_unique_constraint("workouts_uuid_key", "workouts", ["uuid"])

    op.add_column("workouts", sa.Column("plan_day_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "workouts_plan_day_id_fkey", "workouts", "plan_days", ["plan_day_id"], ["id"], ondelete="SET NULL"
    )
    op.add_column("workouts", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    for column in ("created_at", "updated_at"):
        op.add_column(
            "workouts",
            sa.Column(column, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    op.create_index("ix_workouts_user_performed", "workouts", ["user_id", "performed_at"])


def downgrade() -> None:
    op.drop_index("ix_workouts_user_performed", table_name="workouts")
    for column in ("updated_at", "created_at", "duration_seconds"):
        op.drop_column("workouts", column)
    op.drop_constraint("workouts_plan_day_id_fkey", "workouts", type_="foreignkey")
    op.drop_column("workouts", "plan_day_id")
    op.drop_constraint("workouts_uuid_key", "workouts", type_="unique")
    op.drop_column("workouts", "uuid")
    op.alter_column("workouts", "performed_at", new_column_name="date")
    op.alter_column(
        "workouts",
        "date",
        type_=sa.DateTime(),
        postgresql_using="date AT TIME ZONE 'UTC'",
        nullable=True,
    )

    for table, column, referred, name in CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, referred, [column], ["id"])

    for table in ORDER_COLUMNS:
        op.alter_column(table, "order", nullable=True, server_default=None)
    op.alter_column("plans", "is_public", nullable=True, server_default=None)

    op.create_table(
        "user_active_plans",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("plans.id"), primary_key=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )
    op.execute(
        "INSERT INTO user_active_plans (user_id, plan_id, is_active) "
        "SELECT id, active_plan_id, true FROM users WHERE active_plan_id IS NOT NULL"
    )
    op.drop_constraint("users_active_plan_id_fkey", "users", type_="foreignkey")
    op.drop_column("users", "active_plan_id")
    op.alter_column("users", "is_superuser", nullable=True, server_default=None)
    op.alter_column("users", "is_active", nullable=True, server_default=None)
