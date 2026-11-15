"""spotify links

Revision ID: a9d4e2f6c8b1
Revises: f7a3c1e9b2d4
Create Date: 2026-11-15 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9d4e2f6c8b1"
down_revision: str | None = "f7a3c1e9b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "spotify_links",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("access_token", sa.Text()),
        sa.Column("refresh_token", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("pending_state", sa.String(64), unique=True),
        sa.Column("pending_verifier", sa.String(128)),
        sa.Column("pending_redirect", sa.String(300)),
        sa.Column("pending_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("spotify_links")
