"""The achievements (each tier's title is one you can wear), XP and levels.

Written from ACHIEVEMENTS.md at the repo root, the plain-Chinese version the
user edits: `zh` is each title as written there and tests/api/test_progress.py
checks the two still match. What the app shows is the English. Metrics are
computed by app/services/progress.py.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field

# XP: per workout, per working set (up to a cap per workout), per record, and a
# bonus on the first workout of each week of a streak (from the second week).
RULES = {
    "workout": 50,
    "working_set": 10,
    "max_sets_per_workout": 30,
    "pr": 25,
    "streak_bonus_per_week": 10,
    "streak_bonus_max": 100,
    # Total XP to reach level L: level_step × L × (L − 1).
    "level_step": 50,
}

CATEGORIES = [
    ("consistency", "Consistency"),
    ("level", "Level"),
    ("strength", "Strength"),
    ("volume", "Volume"),
    ("variety", "Variety"),
    ("habits", "Habits"),
    ("muscles", "Muscles"),
]

# Body parts and their muscle groups (the frontend's REGIONS in lib/exercises.js).
REGIONS = {
    "chest": ("chest",),
    "back": ("lats", "upper_back", "lower_back"),
    "shoulders": ("front_delts", "side_delts", "rear_delts"),
    "arms": ("biceps", "triceps"),
    "legs": ("quads", "hamstrings", "glutes", "calves"),
    "core": ("core",),
}


@dataclass(frozen=True)
class Tier:
    target: float
    medal: str  # bronze | silver | gold | platinum
    xp: int
    title: str
    zh: str
    description: str


@dataclass(frozen=True)
class Achievement:
    id: str
    category: str
    name: str
    icon: str  # a lucide icon name
    metric: str
    tiers: tuple[Tier, ...]
    params: dict = field(default_factory=dict)
    hidden: bool = False


def _a(id, category, name, icon, metric, tiers, params=None, hidden=False) -> Achievement:
    return Achievement(id, category, name, icon, metric, tuple(Tier(*t) for t in tiers), params or {}, hidden)


def _muscle(id, name, icon, titles) -> Achievement:
    """A muscle group's ladder: 100, 500 and 1000 working sets."""
    tiers = [
        (target, medal, xp, en, zh, f"Do {target:,} working sets for your {name.lower()}.")
        for (target, medal, xp), (zh, en) in zip(((100, "bronze", 100), (500, "silver", 250), (1000, "gold", 500)), titles)
    ]
    return _a(f"muscle_{id}", "muscles", name, icon, "muscle_sets", tiers, {"muscle": id})


ACHIEVEMENTS: list[Achievement] = [
    # ---- consistency ----
    _a("workouts", "consistency", "Workouts Logged", "dumbbell", "workouts", [
        (1, "bronze", 100, "First Rep", "初出茅廬", "Log your first workout."),
        (10, "bronze", 150, "Regular", "常客", "Log 10 workouts."),
        (25, "silver", 200, "Committed", "說到做到", "Log 25 workouts."),
        (50, "silver", 250, "Dedicated", "死忠派", "Log 50 workouts."),
        (100, "gold", 400, "Centurion", "百鍊成鋼", "Log 100 workouts."),
        (250, "gold", 500, "Iron Devotee", "鐵粉", "Log 250 workouts."),
        (500, "platinum", 750, "Gym Rat", "健身房住民", "Log 500 workouts."),
        (1000, "platinum", 1000, "Thousand Strong", "千錘百鍊", "Log 1,000 workouts."),
    ]),
    _a("week_streak", "consistency", "Week Streak", "flame", "best_week_streak", [
        (2, "bronze", 100, "On a Roll", "漸入佳境", "Train 2 weeks in a row."),
        (4, "bronze", 150, "Habit Formed", "習慣成自然", "Train 4 weeks in a row."),
        (8, "silver", 250, "Steady", "穩定輸出", "Train 8 weeks in a row."),
        (12, "silver", 350, "Relentless", "風雨無阻", "Train 12 weeks in a row."),
        (26, "gold", 500, "Unbreakable", "堅不可摧", "Train 26 weeks in a row."),
        (52, "platinum", 1000, "Year-Rounder", "全年無休", "Train every week for a year."),
    ]),
    _a("busy_week", "consistency", "Busy Week", "calendar-check", "max_workouts_in_week", [
        (4, "bronze", 100, "Busy Bee", "小蜜蜂", "Train 4 times in one week."),
        (5, "silver", 200, "Overachiever", "超標達人", "Train 5 times in one week."),
        (6, "gold", 300, "Almost Daily", "幾乎天天", "Train 6 times in one week."),
    ]),
    _a("comeback", "consistency", "Comeback", "rotate-ccw", "comebacks", [
        (1, "bronze", 150, "Comeback Kid", "王者歸來", "Get back to it after more than two weeks off."),
    ], {"gap_days": 14}),
    # ---- level (no XP: levelling up must not level you up) ----
    _a("level", "level", "Level", "star", "level", [
        (5, "bronze", 0, "Apprentice", "學徒", "Reach level 5."),
        (10, "bronze", 0, "Lifter", "舉鐵人", "Reach level 10."),
        (15, "silver", 0, "Grinder", "苦練者", "Reach level 15."),
        (20, "silver", 0, "Veteran", "老手", "Reach level 20."),
        (30, "gold", 0, "Elite", "菁英", "Reach level 30."),
        (40, "gold", 0, "Titan", "泰坦", "Reach level 40."),
        (50, "platinum", 0, "Legend", "傳奇", "Reach level 50."),
    ]),
    # ---- strength ----
    _a("prs", "strength", "Personal Records", "trophy", "prs", [
        (1, "bronze", 100, "Record Setter", "初次突破", "Set your first PR."),
        (10, "bronze", 150, "Rising", "步步高升", "Set 10 PRs."),
        (50, "silver", 300, "Record Breaker", "紀錄粉碎機", "Set 50 PRs."),
        (100, "gold", 500, "Limit Pusher", "挑戰極限", "Set 100 PRs."),
        (250, "platinum", 1000, "Unstoppable", "勢不可擋", "Set 250 PRs."),
    ]),
    _a("bench_bw", "strength", "Bench vs Body Weight", "scale", "bodyweight_ratio", [
        (1.0, "silver", 400, "Bodyweight Bencher", "推起自己", "Bench press your body weight."),
        (1.5, "gold", 800, "Bench Boss", "臥推老大", "Bench press 1.5× your body weight."),
    ], {"exercises": ["Bench Press"], "body_weight_within_days": 30}),
    _a("squat_bw", "strength", "Squat vs Body Weight", "scale", "bodyweight_ratio", [
        (1.5, "silver", 400, "Strong Legs", "鐵腿", "Squat 1.5× your body weight."),
        (2.0, "gold", 800, "Tree Trunks", "神木腿", "Squat twice your body weight."),
    ], {"exercises": ["Squat"], "body_weight_within_days": 30}),
    _a("deadlift_bw", "strength", "Deadlift vs Body Weight", "scale", "bodyweight_ratio", [
        (2.0, "silver", 400, "Heavy Puller", "硬舉狠角色", "Deadlift twice your body weight."),
        (2.5, "gold", 800, "Ground Shaker", "撼地者", "Deadlift 2.5× your body weight."),
    ], {"exercises": ["Deadlift"], "body_weight_within_days": 30}),
    _a("pullups", "strength", "Pull-ups", "arrow-up-from-line", "max_reps", [
        (1, "bronze", 150, "Off the Ground", "離開地面", "Do a pull-up."),
        (10, "silver", 300, "Pull-up Pro", "引體高手", "Do 10 pull-ups in one set."),
        (20, "gold", 600, "Sky Climber", "攀天者", "Do 20 pull-ups in one set."),
    ], {"exercises": ["Pull-up", "Chin-up"]}),
    _a("pushups", "strength", "Push-ups", "arrow-down-to-line", "max_reps", [
        (25, "bronze", 150, "Pusher", "推地者", "Do 25 push-ups in one set."),
        (50, "silver", 300, "Push-up Machine", "人體打樁機", "Do 50 push-ups in one set."),
    ], {"exercises": ["Push-up"]}),
    # ---- volume ----
    _a("lifetime_volume", "volume", "Lifetime Volume", "mountain", "total_volume_kg", [
        (10_000, "bronze", 150, "Ten Tonner", "十噸起跳", "Lift 10 t in total."),
        (100_000, "silver", 300, "Heavy Hauler", "百噸搬運工", "Lift 100 t in total."),
        (500_000, "gold", 600, "Mountain Mover", "愚公移山", "Lift 500 t in total."),
        (1_000_000, "platinum", 1000, "Megatonner", "千噸傳說", "Lift 1,000 t in total."),
    ]),
    _a("big_day", "volume", "Big Day", "rocket", "max_workout_volume_kg", [
        (5_000, "bronze", 150, "Big Day", "爆量日", "Lift 5 t in one workout."),
        (10_000, "silver", 300, "Ten-Ton Session", "十噸一場", "Lift 10 t in one workout."),
        (20_000, "gold", 600, "Beast Mode", "野獸模式", "Lift 20 t in one workout."),
    ]),
    _a("sets", "volume", "Working Sets", "layers", "working_sets", [
        (500, "bronze", 150, "Set Stacker", "疊組達人", "Log 500 working sets."),
        (2000, "silver", 300, "Volume Junkie", "訓練量成癮", "Log 2,000 working sets."),
        (5000, "gold", 600, "Set Machine", "做組機器", "Log 5,000 working sets."),
    ]),
    # ---- variety ----
    _a("exercises", "variety", "Exercises Tried", "shapes", "distinct_exercises", [
        (10, "bronze", 100, "Curious", "好奇寶寶", "Do 10 different exercises."),
        (25, "silver", 250, "Explorer", "探險家", "Do 25 different exercises."),
        (50, "gold", 500, "Encyclopedia", "動作百科", "Do 50 different exercises."),
    ]),
    _a("full_body_week", "variety", "Full Body Week", "person-standing", "full_body_weeks", [
        (1, "bronze", 200, "Well-Rounded", "面面俱到", "Train every body part in one week."),
        (10, "silver", 400, "Balanced", "全面發展", "Train every body part in a week, 10 times."),
    ]),
    _a("supersets", "variety", "Supersets", "link-2", "superset_workouts", [
        (10, "bronze", 150, "Superset Fan", "超級組愛好者", "Use a superset in 10 workouts."),
        (50, "silver", 300, "Efficiency Expert", "效率專家", "Use a superset in 50 workouts."),
    ]),
    # ---- habits ----
    _a("early_bird", "habits", "Early Bird", "sunrise", "workouts_started_before", [
        (10, "silver", 300, "Early Bird", "早起的鳥兒", "Start 10 workouts before 7 am."),
    ], {"hour": 7}),
    _a("night_owl", "habits", "Night Owl", "moon", "workouts_started_after", [
        (10, "silver", 300, "Night Owl", "夜貓子", "Start 10 workouts after 9 pm."),
    ], {"hour": 21}),
    _a("marathon", "habits", "Marathon", "hourglass", "workouts_longer_than", [
        (1, "bronze", 200, "Marathoner", "馬拉松", "Train for more than 2 hours."),
    ], {"minutes": 120}),
    _a("weekend_warrior", "habits", "Weekend Warrior", "calendar-days", "weekends_both_days", [
        (5, "silver", 300, "Weekend Warrior", "週末戰士", "Train on both Saturday and Sunday, 5 weekends."),
    ]),
    _a("weigh_ins", "habits", "Weigh-ins", "weight", "body_weight_entries", [
        (10, "bronze", 100, "Tracker", "紀錄控", "Log your body weight 10 times."),
        (50, "silver", 250, "Data Nerd", "數據狂", "Log your body weight 50 times."),
    ]),
    _a("new_year", "habits", "New Year", "party-popper", "workouts_on_date", [
        (1, "gold", 300, "Resolution Keeper", "新年新希望", "Train on New Year's Day."),
    ], {"month": 1, "day": 1}, hidden=True),
    # ---- muscles ----
    _muscle("chest", "Chest", "shield", [("胸肌萌芽", "Pec Sprout"), ("胸肌收割機", "Pec Harvester"), ("胸肌終結者", "Chest Terminator")]),
    _muscle("lats", "Lats", "plane", [("準備起飛", "Cleared for Takeoff"), ("人形滑翔翼", "Human Glider"), ("背闊終結者", "Lat Terminator")]),
    _muscle("upper_back", "Upper Back", "ship", [("划船新手", "Row Rookie"), ("背部收割機", "Back Harvester"), ("上背終結者", "Upper Back Terminator")]),
    _muscle("lower_back", "Lower Back", "anchor", [("腰桿挺直", "Standing Tall"), ("鋼鐵腰", "Iron Spine"), ("下背終結者", "Lower Back Terminator")]),
    _muscle("front_delts", "Front Delts", "arrow-up", [("前排觀眾", "Front Row Seat"), ("肩推收割機", "Press Harvester"), ("前三角終結者", "Front Delt Terminator")]),
    _muscle("side_delts", "Side Delts", "move-horizontal", [("肩膀加寬中", "Widening in Progress"), ("人形衣架", "Human Coat Hanger"), ("側三角終結者", "Side Delt Terminator")]),
    _muscle("rear_delts", "Rear Delts", "eye", [("後照鏡", "Rear View Mirror"), ("後三角收割機", "Rear Delt Harvester"), ("後三角終結者", "Rear Delt Terminator")]),
    _muscle("biceps", "Biceps", "biceps-flexed", [("小老鼠", "Little Mouse"), ("槍砲秀", "Gun Show"), ("二頭終結者", "Biceps Terminator")]),
    _muscle("triceps", "Triceps", "magnet", [("蝴蝶袖退散", "Bye-Bye Bingo Wings"), ("馬蹄鐵", "Horseshoe"), ("三頭終結者", "Triceps Terminator")]),
    _muscle("quads", "Quads", "zap", [("大腿覺醒", "Thigh Awakening"), ("雷神大腿", "Thunder Thighs"), ("股四頭終結者", "Quad Terminator")]),
    _muscle("hamstrings", "Hamstrings", "wheat", [("腿後好緊", "Tight Hammies"), ("腿後收割機", "Hamstring Harvester"), ("腿後終結者", "Hamstring Terminator")]),
    _muscle("glutes", "Glutes", "apple", [("蜜桃初長成", "Peach Sprout"), ("蜜桃農夫", "Peach Farmer"), ("臀部終結者", "Glute Terminator")]),
    _muscle("calves", "Calves", "beef", [("頑固小腿", "Stubborn Calves"), ("小牛變大牛", "From Calf to Cow"), ("小腿終結者", "Calf Terminator")]),
    _muscle("core", "Core", "layout-grid", [("六塊肌載入中", "Six-Pack Loading"), ("洗衣板", "Washboard"), ("核心終結者", "Core Terminator")]),
    _a("leg_day", "muscles", "Leg Day", "footprints", "region_week_streak", [
        (4, "bronze", 150, "Never Skips Leg Day", "不翹腿日", "Train legs (3+ sets) 4 weeks in a row."),
        (12, "silver", 300, "Leg Day Honor Roll", "腿日模範生", "Train legs (3+ sets) 12 weeks in a row."),
        (26, "gold", 600, "Leg Day Legend", "腿日傳說", "Train legs (3+ sets) 26 weeks in a row."),
    ], {"region": "legs", "min_sets": 3}),
    _a("chest_day", "muscles", "International Chest Day", "calendar-heart", "region_weekdays", [
        (10, "silver", 200, "International Chest Day Delegate", "國際胸日代表", "Train chest (3+ sets) on 10 Mondays."),
    ], {"region": "chest", "weekday": 0, "min_sets": 3}),
    _a("arm_day", "muscles", "Arm Day", "shirt", "max_workout_region_sets", [
        (15, "bronze", 150, "Sleeve Destroyer", "袖子殺手", "Do 15 sets of biceps and triceps in one workout."),
    ], {"region": "arms"}),
    _a("chicken_legs", "muscles", "Chicken Legs", "drumstick", "chicken_legs", [
        (1, "bronze", 50, "Chicken Legs", "鳥仔腳", "Over 4 weeks, train chest and arms 3× as much as legs."),
    ], {"days": 28, "ratio": 3, "min_sets": 30}, hidden=True),
]

BY_ID = {a.id: a for a in ACHIEVEMENTS}

# Moves whenever a definition does, so clients refetch (GET /sync/state).
VERSION = hashlib.sha1(
    json.dumps([RULES, [asdict(a) for a in ACHIEVEMENTS]], sort_keys=True, default=str).encode()
).hexdigest()[:12]


def title_key(achievement: Achievement, tier: Tier) -> str:
    return f"{achievement.id}:{tier.target:.10g}"  # 1000000 stays "1000000", 1.0 is "1"


def find_tier(key: str) -> tuple[Achievement, Tier] | None:
    """The tier a title key names, if it still exists."""
    achievement_id, _, target = key.partition(":")
    achievement = BY_ID.get(achievement_id)
    if achievement is None:
        return None
    try:
        value = float(target)
    except ValueError:
        return None
    return next(((achievement, t) for t in achievement.tiers if t.target == value), None)


def level_for(xp: int) -> int:
    """The level `xp` reaches: the highest L with level_step × L × (L − 1) <= xp."""
    level = 1
    while RULES["level_step"] * (level + 1) * level <= xp:
        level += 1
    return level


def xp_for_level(level: int) -> int:
    return RULES["level_step"] * level * (level - 1)
