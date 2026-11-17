"""split the arms muscle group into biceps and triceps

Revision ID: e1f3b5c7a9d2
Revises: d4f8a2c6e1b7
Create Date: 2026-11-18 00:00:00

Library entries and exercises filed under "arms" are sorted by name: curls are
biceps; pushdowns, extensions, skull crushers, close-grip presses and dips are
triceps; anything else (forearms, say) becomes "other". updated_at moves, so
devices see the change and download the library and their exercises again.
The API sorts an "arms" sent by older app versions the same way
(app/schemas/exercise.py).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e1f3b5c7a9d2"
down_revision: str | None = "d4f8a2c6e1b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed here (not imported) so later code changes can't change what this did.
TRICEPS = ("tricep", "pushdown", "push-down", "skull", "extension", "kickback", "close-grip", "dip", "三頭", "下壓", "伸展", "窄握", "撐體")
BICEPS = ("curl", "bicep", "彎舉", "二頭")


def _any(text: str, words: Sequence[str]) -> str:
    return " OR ".join(f"{text} LIKE '%{word}%'" for word in words)


def _split(table: str, text: str) -> None:
    op.execute(
        f"""
        UPDATE {table}
        SET muscle_group = CASE
                WHEN {_any(text, TRICEPS)} THEN 'triceps'
                WHEN {_any(text, BICEPS)} THEN 'biceps'
                ELSE 'other'
            END,
            updated_at = now()
        WHERE muscle_group = 'arms'
        """
    )


def upgrade() -> None:
    _split("catalog_exercises", "lower(name || ' ' || coalesce(zh, '') || ' ' || coalesce(aka, ''))")
    _split("exercises", "lower(name)")


def downgrade() -> None:
    for table in ("catalog_exercises", "exercises"):
        op.execute(
            f"UPDATE {table} SET muscle_group = 'arms', updated_at = now() WHERE muscle_group IN ('biceps', 'triceps')"
        )
