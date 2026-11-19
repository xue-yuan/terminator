"""XP, levels and achievements (GET /progress): replayed from the whole history,
banked as earned, never taken back."""

import re
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.achievements import ACHIEVEMENTS, RULES, level_for, xp_for_level

pytestmark = pytest.mark.anyio

URL = "/api/v1/progress"
DOC = Path(__file__).parents[2] / "ACHIEVEMENTS.md"


async def exercise(client, h, name: str, group: str) -> str:
    id_ = str(uuid.uuid4())
    r = await client.put(f"/api/v1/exercises/{id_}", json={"name": name, "muscle_group": group}, headers=h)
    assert r.status_code in (200, 201), r.text
    return id_


def sets(n: int, weight: float = 50, reps: int = 8, **extra) -> list[dict]:
    return [{"weight": weight, "reps": reps, **extra} for _ in range(n)]


async def workout(client, h, at: str, items: list[dict], duration: int | None = 3600, id_: str | None = None) -> str:
    id_ = id_ or str(uuid.uuid4())
    body = {"name": "W", "performed_at": at, "duration_seconds": duration, "items": items}
    r = await client.put(f"/api/v1/workouts/{id_}", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return id_


async def progress(client, h, tz: str = "UTC") -> dict:
    r = await client.get(URL, params={"tz": tz}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def achievement(p: dict, id_: str) -> dict:
    return next(a for a in p["achievements"] if a["id"] == id_)


def unlocked(p: dict, id_: str) -> list[float]:
    return [t["target"] for t in achievement(p, id_)["tiers"] if t["unlocked_at"]]


async def test_a_new_user_starts_at_level_1_with_secrets_kept(client, user):
    p = await progress(client, user["headers"])
    assert (p["xp"], p["level"], p["level_xp"], p["next_level_xp"], p["title"]) == (0, 1, 0, 100, None)
    assert p["rules"] == RULES
    assert [c["id"] for c in p["categories"]][:2] == ["consistency", "level"]
    assert len(p["achievements"]) == len(ACHIEVEMENTS)
    assert not any(t["unlocked_at"] for a in p["achievements"] for t in a["tiers"])
    secret = achievement(p, "new_year")
    assert secret["hidden"] and secret["name"] is None and secret["tiers"][0]["title"] is None
    assert achievement(p, "workouts")["name"] == "Workouts Logged"


async def test_a_workout_earns_xp_and_its_first_titles(client, user):
    h = user["headers"]
    bench = await exercise(client, h, "Bench Press", "chest")
    # 12 working sets (capped at 30), warm-ups count for nothing.
    wid = await workout(
        client,
        h,
        "2026-11-17T18:00:00Z",
        [{"exercise_id": bench, "exercise_name": "Bench Press", "sets": sets(2, 20, kind="warmup") + sets(12)}],
    )
    p = await progress(client, h)
    workout_xp = RULES["workout"] + 12 * RULES["working_set"]
    assert p["xp"] == workout_xp + 100  # + "First Rep"
    assert p["level"] == level_for(p["xp"]) == 2  # level 3 starts at 300
    tier = achievement(p, "workouts")["tiers"][0]
    assert tier["title"] == "First Rep" and tier["workout_id"] == wid
    assert tier["unlocked_at"].startswith("2026-11-17T18:00")
    assert achievement(p, "sets")["value"] == 12
    assert achievement(p, "muscle_chest")["value"] == 12


async def test_earned_xp_and_titles_are_never_taken_back(client, user):
    h = user["headers"]
    big = sets(30)
    wid = await workout(client, h, "2026-11-17T18:00:00Z", [{"exercise_name": "Squat", "sets": big}])
    before = await progress(client, h)
    assert unlocked(before, "workouts") == [1]

    # Edited down to one set: still worth what it was.
    await workout(client, h, "2026-11-17T18:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}], id_=wid)
    assert (await progress(client, h))["xp"] == before["xp"]
    # Deleted: the XP and the title stay.
    assert (await client.delete(f"/api/v1/workouts/{wid}", headers=h)).status_code == 204
    after = await progress(client, h)
    assert after["xp"] == before["xp"]
    assert unlocked(after, "workouts") == [1]
    assert achievement(after, "workouts")["value"] == 0  # the count itself is honest


async def test_editing_a_workout_up_raises_its_xp(client, user):
    h = user["headers"]
    wid = await workout(client, h, "2026-11-17T18:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}])
    low = (await progress(client, h))["xp"]
    await workout(client, h, "2026-11-17T18:00:00Z", [{"exercise_name": "Squat", "sets": sets(5)}], id_=wid)
    assert (await progress(client, h))["xp"] == low + 4 * RULES["working_set"]


async def test_records_and_streak_bonus(client, user):
    h = user["headers"]
    # Three Mondays in a row, heavier each time: the 2nd and 3rd set PRs.
    for week, weight in enumerate((100, 105, 110)):
        await workout(client, h, f"2026-11-{2 + 7 * week:02d}T18:00:00Z", [{"exercise_name": "Squat", "sets": sets(1, weight)}])
    p = await progress(client, h)
    base = RULES["workout"] + RULES["working_set"]
    streak = RULES["streak_bonus_per_week"] * 2 + RULES["streak_bonus_per_week"] * 3  # weeks 2 and 3
    tiers = 100 + 100 + 100  # First Rep, On a Roll (2 weeks), Record Setter
    assert p["xp"] == 3 * base + 2 * RULES["pr"] + streak + tiers
    assert achievement(p, "prs")["value"] == 2
    assert achievement(p, "week_streak")["value"] == 3


async def test_levels_unlock_their_titles(client, user):
    h = user["headers"]
    for day in (2, 3, 4):  # 3 × 350 XP + First Rep (light, so no volume titles)
        await workout(client, h, f"2026-11-{day:02d}T18:00:00Z", [{"exercise_name": "Leg Press", "sets": sets(30, 10, 5)}])
    p = await progress(client, h)
    assert p["level"] == 5 and p["xp"] >= xp_for_level(5)
    assert unlocked(p, "level") == [5]
    assert achievement(p, "level")["value"] == 5


async def test_consistency_rules(client, user):
    h = user["headers"]
    for day in ("2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08"):  # 4 in one week
        await workout(client, h, f"{day}T18:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}])
    await workout(client, h, "2026-10-25T18:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}])  # 17 days later
    p = await progress(client, h)
    assert achievement(p, "busy_week")["value"] == 4 and unlocked(p, "busy_week") == [4]
    assert unlocked(p, "comeback") == [1]


async def test_a_comeback_takes_more_than_14_days_off(client, user):
    h = user["headers"]
    squat = [{"exercise_name": "Squat", "sets": sets(1)}]
    await workout(client, h, "2026-11-01T18:00:00Z", squat)
    await workout(client, h, "2026-11-16T18:00:00Z", squat)  # 2nd to 15th off: 14 days, not more
    p = await progress(client, h)
    assert achievement(p, "comeback")["value"] == 0
    await workout(client, h, "2026-12-02T18:00:00Z", squat)  # 17th to 1st off: 15 days
    p = await progress(client, h)
    assert achievement(p, "comeback")["value"] == 1 and unlocked(p, "comeback") == [1]


async def test_muscle_rules(client, user):
    h = user["headers"]
    groups = {
        "Bench Press": "chest",
        "Lat Pulldown": "lats",
        "Lateral Raise": "side_delts",
        "Curl": "biceps",
        "Pushdown": "triceps",
        "Squat": "quads",
        "Crunch": "core",
    }
    ids = {name: await exercise(client, h, name, group) for name, group in groups.items()}

    def item(name, n):
        return {"exercise_id": ids[name], "exercise_name": name, "sets": sets(n)}

    # Monday 2 Nov: everything (a full-body week, chest on a Monday, arm day).
    await workout(client, h, "2026-11-02T10:00:00Z", [item(n, 8 if n in ("Curl", "Pushdown") else 3) for n in groups])
    # Legs (3+ sets) in each of the next three weeks: 4 weeks in a row.
    for day in (10, 17, 24):
        await workout(client, h, f"2026-11-{day:02d}T10:00:00Z", [item("Squat", 3)])
    p = await progress(client, h)
    assert unlocked(p, "full_body_week") == [1]
    assert unlocked(p, "arm_day") == [15]
    assert achievement(p, "chest_day")["value"] == 1
    assert achievement(p, "leg_day")["value"] == 4 and unlocked(p, "leg_day") == [4]
    assert achievement(p, "muscle_quads")["value"] == 12
    assert achievement(p, "muscle_biceps")["value"] == 8


async def test_chicken_legs_is_a_secret_until_earned(client, user):
    h = user["headers"]
    bench = await exercise(client, h, "Bench Press", "chest")
    squat = await exercise(client, h, "Squat", "quads")
    assert achievement(await progress(client, h), "chicken_legs")["name"] is None
    await workout(
        client,
        h,
        "2026-11-02T10:00:00Z",
        [
            {"exercise_id": bench, "exercise_name": "Bench Press", "sets": sets(30)},
            {"exercise_id": squat, "exercise_name": "Squat", "sets": sets(5)},
        ],
    )
    p = await progress(client, h)
    legs = achievement(p, "chicken_legs")
    assert legs["name"] == "Chicken Legs" and legs["tiers"][0]["title"] == "Chicken Legs"
    assert unlocked(p, "chicken_legs") == [1]


async def test_body_weight_rules(client, user):
    h = user["headers"]
    bench = await exercise(client, h, "Bench Press", "chest")
    for i in range(10):
        entry = {"measured_at": f"2026-10-{1 + i:02d}T07:00:00Z", "weight": 176, "unit": "lb"}  # 79.8 kg
        await client.put(f"/api/v1/body-weights/{uuid.uuid4()}", json=entry, headers=h)
    item = {"exercise_id": bench, "exercise_name": "Bench Press", "sets": sets(1, 80, 3)}
    await workout(client, h, "2026-10-20T18:00:00Z", [item])
    # Two months after the last weigh-in: no body weight to compare against.
    late = {"exercise_id": bench, "exercise_name": "Bench Press", "sets": sets(1, 125, 1)}
    await workout(client, h, "2026-12-20T18:00:00Z", [late])
    p = await progress(client, h)
    assert unlocked(p, "bench_bw") == [1.0]
    assert achievement(p, "bench_bw")["value"] == pytest.approx(80 / (176 * 0.45359237), abs=0.01)
    assert unlocked(p, "weigh_ins") == [10]
    assert achievement(p, "weigh_ins")["tiers"][0]["workout_id"] is None


async def test_times_of_day_are_the_users(client, user):
    h = user["headers"]
    # 22:30 UTC is 06:30 the next morning in Taipei.
    for day in range(1, 11):
        await workout(client, h, f"2026-03-{day:02d}T22:30:00Z", [{"exercise_name": "Squat", "sets": sets(1)}])
    assert unlocked(await progress(client, h, "Asia/Taipei"), "early_bird") == [10]
    # Banked: asking in another time zone doesn't take it away.
    assert unlocked(await progress(client, h, "UTC"), "early_bird") == [10]
    assert achievement(await progress(client, h, "UTC"), "night_owl")["value"] == 10


async def test_habit_rules(client, user):
    h = user["headers"]
    await workout(client, h, "2026-01-01T10:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}], duration=7300)
    for week in range(5):
        saturday = date(2026, 1, 3) + timedelta(weeks=week)
        for day in (saturday, saturday + timedelta(days=1)):
            await workout(client, h, f"{day.isoformat()}T10:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}])
    p = await progress(client, h)
    assert unlocked(p, "new_year") == [1] and achievement(p, "new_year")["name"] == "New Year"
    assert unlocked(p, "marathon") == [1]
    assert unlocked(p, "weekend_warrior") == [5]


async def test_supersets_and_variety(client, user):
    h = user["headers"]
    items = [
        {"exercise_name": f"Move {i}", "superset": 1 if i < 2 else None, "sets": sets(1)} for i in range(10)
    ]
    await workout(client, h, "2026-11-02T10:00:00Z", items)
    p = await progress(client, h)
    assert achievement(p, "supersets")["value"] == 1
    assert unlocked(p, "exercises") == [10]


async def test_wearing_a_title(client, user):
    h = user["headers"]
    await workout(client, h, "2026-11-02T10:00:00Z", [{"exercise_name": "Squat", "sets": sets(1)}])
    await progress(client, h)

    async def state():
        return (await client.get("/api/v1/sync/state", headers=h)).json()["progress"]

    before = await state()
    r = await client.put(f"{URL}/title", json={"title": "workouts:1"}, headers=h)
    assert r.status_code == 200 and r.json() == {"key": "workouts:1", "title": "First Rep", "medal": "bronze"}
    assert (await progress(client, h))["title"]["title"] == "First Rep"
    assert await state() != before  # devices pick it up

    assert (await client.put(f"{URL}/title", json={"title": "workouts:100"}, headers=h)).status_code == 404
    assert (await client.put(f"{URL}/title", json={"title": "nonsense"}, headers=h)).status_code == 404
    assert (await client.put(f"{URL}/title", json={"title": None}, headers=h)).json() is None
    assert (await progress(client, h))["title"] is None


async def test_needs_sign_in_and_a_real_time_zone(client, user):
    assert (await client.get(URL)).status_code == 401
    assert (await client.get(URL, params={"tz": "Mars/Olympus"}, headers=user["headers"])).status_code == 422


def test_the_rules_match_the_plain_chinese_version():
    """ACHIEVEMENTS.md is what gets edited; every title there (above 「先不做」)
    is in the code, in the same order, with the English it gives. It is kept out
    of git, so a fresh clone has nothing to compare against."""
    if not DOC.exists():
        pytest.skip("ACHIEVEMENTS.md is not in this checkout")
    doc = DOC.read_text().split("## 先不做")[0]
    written = re.findall(r"→「([^」]+)」\(([^)]+)\)", doc)
    coded = [(t.zh, t.title) for a in ACHIEVEMENTS for t in a.tiers]
    assert coded == written
    titles = [t.title for a in ACHIEVEMENTS for t in a.tiers]
    assert len(titles) == len(set(titles)), "every title is different"


async def test_title_keys_name_big_and_fractional_targets_plainly(client, user):
    from app.services.achievements import BY_ID, find_tier, title_key

    big = BY_ID["lifetime_volume"]
    assert title_key(big, big.tiers[-1]) == "lifetime_volume:1000000"
    bench = BY_ID["bench_bw"]
    assert [title_key(bench, t) for t in bench.tiers] == ["bench_bw:1", "bench_bw:1.5"]
    assert find_tier("bench_bw:1.5")[1].title == "Bench Boss"
