"""allowed emails (who admins let in)

Revision ID: b2c7e4a1d9f5
Revises: a9d4e2f6c8b1
Create Date: 2026-11-16 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c7e4a1d9f5"
down_revision: str | None = "a9d4e2f6c8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "allowed_emails",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("allowed_emails")
