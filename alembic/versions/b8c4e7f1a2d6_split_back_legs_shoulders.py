"""split back, legs and shoulders into muscles

Revision ID: b8c4e7f1a2d6
Revises: c6a1f8d3e9b4
Create Date: 2026-11-18 12:00:00

Library entries and exercises filed under the old groups are sorted by name:
- back: face pulls are rear delts; deadlifts, rack pulls and back extensions are
  lower back; pull-ups, chin-ups, pulldowns and pullovers are lats; the rest
  (rows, shrugs) is upper back
- shoulders: rear delt flies and face pulls are rear delts; lateral raises and
  upright rows are side delts; the rest (presses, front raises) is front delts
- legs: calf raises are calves; Romanian deadlifts and leg curls are hamstrings;
  hip thrusts, sumo deadlifts and hip abduction/adduction are glutes (and
  hips); the rest (squats, presses, lunges, extensions) is quads
updated_at moves, so devices see the change and download the library and their
exercises again. The API sorts an old group sent by older app versions the same
way (app/schemas/exercise.py).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b8c4e7f1a2d6"
down_revision: str | None = "c6a1f8d3e9b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Fixed here (not imported) so later code changes can't change what this did.
RULES: dict[str, tuple[list[tuple[str, tuple[str, ...]]], str]] = {
    "back": (
        [
            ("rear_delts", ("face pull", "facepull", "rear delt", "臉拉", "後三角")),
            ("lower_back", ("deadlift", "rack pull", "back extension", "hyperextension", "good morning", "硬舉", "背伸展", "山羊挺身", "羅馬椅", "下背", "早安")),
            ("lats", ("pull-up", "pullup", "pull up", "chin-up", "chinup", "chin up", "pulldown", "pull-down", "pull down", "lat pull", "lats", "pullover", "引體", "下拉", "背闊", "直臂")),
        ],
        "upper_back",
    ),
    "shoulders": (
        [
            ("rear_delts", ("rear", "reverse fly", "reverse pec", "face pull", "後三角", "反向飛鳥", "臉拉", "後束")),
            ("side_delts", ("lateral", "side raise", "upright", "y raise", "側平舉", "側三角", "直立划船", "側束")),
        ],
        "front_delts",
    ),
    "legs": (
        [
            ("calves", ("calf", "calves", "提踵", "小腿")),
            ("hamstrings", ("romanian", "rdl", "leg curl", "hamstring", "glute-ham", "nordic", "good morning", "stiff-leg", "stiff leg", "腿彎舉", "腿後", "羅馬尼亞", "直腿", "早安")),
            ("glutes", ("hip thrust", "glute", "abduct", "adduct", "kickback", "sumo", "bridge", "臀", "外展", "內收", "相撲", "髖")),
        ],
        "quads",
    ),
}
# Downgrading files each muscle under its old body part (so a face pull that
# was under back comes back under shoulders).
OLD = {
    "back": ("lats", "upper_back", "lower_back"),
    "shoulders": ("front_delts", "side_delts", "rear_delts"),
    "legs": ("quads", "hamstrings", "glutes", "calves"),
}


def _any(text: str, words: Sequence[str]) -> str:
    return " OR ".join(f"{text} LIKE '%{word}%'" for word in words)


def _split(table: str, text: str) -> None:
    for old, (rules, fallback) in RULES.items():
        cases = " ".join(f"WHEN {_any(text, words)} THEN '{group}'" for group, words in rules)
        op.execute(
            f"""
            UPDATE {table}
            SET muscle_group = CASE {cases} ELSE '{fallback}' END,
                updated_at = now()
            WHERE muscle_group = '{old}'
            """
        )


def upgrade() -> None:
    _split("catalog_exercises", "lower(name || ' ' || coalesce(zh, '') || ' ' || coalesce(aka, ''))")
    _split("exercises", "lower(name)")


def downgrade() -> None:
    for table in ("catalog_exercises", "exercises"):
        for old, muscles in OLD.items():
            listed = ", ".join(f"'{m}'" for m in muscles)
            op.execute(f"UPDATE {table} SET muscle_group = '{old}', updated_at = now() WHERE muscle_group IN ({listed})")
