"""exercise library (built-in catalog, edited by admins)

Revision ID: d4f8a2c6e1b7
Revises: b2c7e4a1d9f5
Create Date: 2026-11-16 00:00:00

Moves the catalog that used to be hard-coded in the frontend
(src/lib/exercises.js) into the database, so admins can change it from the app.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4f8a2c6e1b7"
down_revision: str | None = "b2c7e4a1d9f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (name, Chinese name, other names, muscle group): the catalog as it was in the frontend.
SEED = [
    # chest
    ("Bench Press", "槓鈴臥推", None, "chest"),
    ("Incline Bench Press", "上斜槓鈴臥推", None, "chest"),
    ("Decline Bench Press", "下斜臥推", None, "chest"),
    ("Dumbbell Bench Press", "啞鈴臥推", None, "chest"),
    ("Incline Dumbbell Press", "上斜啞鈴臥推", None, "chest"),
    ("Chest Press Machine", "坐姿推胸機", "機械中胸 機械推胸", "chest"),
    ("Incline Chest Press Machine", "上斜推胸機", "機械上胸", "chest"),
    ("Decline Chest Press Machine", "下斜推胸機", "機械下胸", "chest"),
    ("Dumbbell Fly", "啞鈴飛鳥", None, "chest"),
    ("Cable Fly", "繩索夾胸", None, "chest"),
    ("Pec Deck", "蝴蝶機夾胸", "機械夾胸 蝴蝶機", "chest"),
    ("Decline Fly Machine", "下斜夾胸機", "機械夾下胸", "chest"),
    ("Push-up", "伏地挺身", None, "chest"),
    ("Dips", "雙槓撐體", None, "chest"),
    # back
    ("Deadlift", "硬舉", None, "back"),
    ("Pull-up", "引體向上", None, "back"),
    ("Chin-up", "反手引體向上", None, "back"),
    ("Lat Pulldown", "滑輪下拉", None, "back"),
    ("Barbell Row", "槓鈴划船", None, "back"),
    ("Dumbbell Row", "單臂啞鈴划船", None, "back"),
    ("Seated Cable Row", "坐姿繩索划船", None, "back"),
    ("T-Bar Row", "T 槓划船", None, "back"),
    ("Machine Row", "坐姿划船機", None, "back"),
    ("Straight-Arm Pulldown", "直臂下拉", None, "back"),
    ("Face Pull", "臉拉", None, "back"),
    ("Back Extension", "背伸展", None, "back"),
    ("Shrug", "聳肩", None, "back"),
    # legs
    ("Squat", "槓鈴深蹲", None, "legs"),
    ("Front Squat", "前蹲舉", None, "legs"),
    ("Hack Squat", "哈克深蹲", None, "legs"),
    ("Goblet Squat", "高腳杯深蹲", None, "legs"),
    ("Leg Press", "腿推", None, "legs"),
    ("Romanian Deadlift", "羅馬尼亞硬舉", None, "legs"),
    ("Sumo Deadlift", "相撲硬舉", None, "legs"),
    ("Bulgarian Split Squat", "保加利亞分腿蹲", None, "legs"),
    ("Lunge", "弓箭步", None, "legs"),
    ("Hip Thrust", "臀推", None, "legs"),
    ("Leg Extension", "腿伸展", None, "legs"),
    ("Leg Curl", "腿彎舉", None, "legs"),
    ("Hip Abduction", "髖外展機", None, "legs"),
    ("Hip Adduction", "髖內收機", None, "legs"),
    ("Calf Raise", "站姿提踵", None, "legs"),
    ("Seated Calf Raise", "坐姿提踵", None, "legs"),
    # shoulders
    ("Overhead Press", "槓鈴肩推", None, "shoulders"),
    ("Dumbbell Shoulder Press", "啞鈴肩推", None, "shoulders"),
    ("Machine Shoulder Press", "肩推機", "機械肩推", "shoulders"),
    ("Arnold Press", "阿諾推舉", None, "shoulders"),
    ("Lateral Raise", "側平舉", None, "shoulders"),
    ("Cable Lateral Raise", "繩索側平舉", None, "shoulders"),
    ("Front Raise", "前平舉", None, "shoulders"),
    ("Rear Delt Fly", "反向飛鳥", None, "shoulders"),
    ("Chest-Supported Rear Delt Fly (45°)", "上斜俯身飛鳥 45 度", "肩膀飛鳥", "shoulders"),
    ("Chest-Supported Rear Delt Fly (60°)", "上斜俯身飛鳥 60 度", "肩膀飛鳥", "shoulders"),
    ("Chest-Supported Rear Delt Fly (75°)", "上斜俯身飛鳥 75 度", "肩膀飛鳥", "shoulders"),
    ("Upright Row", "直立划船", None, "shoulders"),
    # arms
    ("Bicep Curl", "槓鈴彎舉", None, "arms"),
    ("Dumbbell Curl", "啞鈴彎舉", None, "arms"),
    ("Hammer Curl", "錘式彎舉", None, "arms"),
    ("Preacher Curl", "牧師椅彎舉", None, "arms"),
    ("Cable Curl", "繩索彎舉", None, "arms"),
    ("Tricep Pushdown", "三頭下壓", None, "arms"),
    ("Overhead Tricep Extension", "過頭三頭伸展", None, "arms"),
    ("Cable Overhead Tricep Extension", "繩索過頭三頭伸展", "三頭上拉", "arms"),
    ("Skull Crusher", "仰臥三頭伸展", None, "arms"),
    ("Close-Grip Bench Press", "窄握臥推", None, "arms"),
    # core
    ("Plank", "棒式", None, "core"),
    ("Side Plank", "側棒式", None, "core"),
    ("Hanging Leg Raise", "懸垂舉腿", None, "core"),
    ("Cable Crunch", "繩索捲腹", None, "core"),
    ("Crunch", "捲腹", None, "core"),
    ("3-Way Crunch", "三向捲腹", "左右捲腹", "core"),
    ("Ab Wheel Rollout", "健腹輪", None, "core"),
    ("Russian Twist", "俄羅斯轉體", None, "core"),
]


def upgrade() -> None:
    table = op.create_table(
        "catalog_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("zh", sa.String(100)),
        sa.Column("aka", sa.String(300)),
        sa.Column("muscle_group", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("uq_catalog_exercises_name", "catalog_exercises", [sa.text("lower(name)")], unique=True)
    op.bulk_insert(
        table,
        [{"name": name, "zh": zh, "aka": aka, "muscle_group": muscle} for name, zh, aka, muscle in SEED],
    )


def downgrade() -> None:
    op.drop_index("uq_catalog_exercises_name", table_name="catalog_exercises")
    op.drop_table("catalog_exercises")
