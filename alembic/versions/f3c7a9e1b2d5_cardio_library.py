"""library: timed holds and cardio

Revision ID: f3c7a9e1b2d5
Revises: e8b1c5d2f4a6
Create Date: 2026-11-23 00:10:00

Planks become timed, and the library gets timed holds and cardio machines,
the latter under a new muscle group, "cardio". Run it once the backend that
knows that group is live (an older one can't list the library with it).
Entries an admin already added under the same name are left as they are.
updated_at moves, so devices download the library again.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f3c7a9e1b2d5"
down_revision: str | None = "e8b1c5d2f4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMED = ("Plank", "Side Plank")

# (name, Chinese name, other names, muscle group, log type)
NEW = [
    ("Wall Sit", "靠牆深蹲", "靠牆蹲 椅子式", "quads", "time"),
    ("Hollow Body Hold", "空心支撐", "船式", "core", "time"),
    ("L-Sit", "L 型支撐", None, "core", "time"),
    ("Dead Hang", "懸吊", "被動懸吊 吊單槓", "other", "time"),
    ("Jump Rope", "跳繩", None, "cardio", "time"),
    ("Running", "跑步", "慢跑 路跑", "cardio", "cardio"),
    ("Treadmill", "跑步機", None, "cardio", "cardio"),
    ("Walking", "健走", "走路 散步", "cardio", "cardio"),
    ("Incline Walk", "坡度走", "爬坡走 跑步機爬坡", "cardio", "cardio"),
    ("Cycling", "騎腳踏車", "單車 自行車", "cardio", "cardio"),
    ("Stationary Bike", "飛輪", "健身車 室內腳踏車", "cardio", "cardio"),
    ("Rowing Machine", "划船機", "有氧划船 飛輪划船", "cardio", "cardio"),
    ("Elliptical", "滑步機", "橢圓機", "cardio", "cardio"),
    ("Stair Climber", "爬梯機", "登階機 樓梯機", "cardio", "cardio"),
    ("Swimming", "游泳", None, "cardio", "cardio"),
    ("Hiking", "登山", "爬山 健行", "cardio", "cardio"),
]


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE catalog_exercises SET log_type = 'time', updated_at = now() WHERE lower(name) IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": [n.lower() for n in TIMED]},
    )
    insert = sa.text(
        "INSERT INTO catalog_exercises (name, zh, aka, muscle_group, log_type) "
        "VALUES (:name, :zh, :aka, :muscle, :log_type) ON CONFLICT (lower(name)) DO NOTHING"
    )
    for name, zh, aka, muscle, log_type in NEW:
        conn.execute(insert, {"name": name, "zh": zh, "aka": aka, "muscle": muscle, "log_type": log_type})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM catalog_exercises WHERE lower(name) IN :names").bindparams(
            sa.bindparam("names", expanding=True)
        ),
        {"names": [n[0].lower() for n in NEW]},
    )
    conn.execute(
        sa.text(
            "UPDATE catalog_exercises SET log_type = 'reps', updated_at = now() WHERE lower(name) IN :names"
        ).bindparams(sa.bindparam("names", expanding=True)),
        {"names": [n.lower() for n in TIMED]},
    )
