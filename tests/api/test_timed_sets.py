"""Timed (a plank) and cardio (a run) sets: logged as a time and/or a distance
with 0 reps, with records of their own, and counted like any working set."""

import uuid

import pytest

from app.services.achievements import RULES

pytestmark = pytest.mark.anyio


async def put_workout(client, h, day: int, items: list[dict], id_: str | None = None) -> dict:
    id_ = id_ or str(uuid.uuid4())
    body = {"performed_at": f"2026-11-{day:02d}T08:00:00Z", "duration_seconds": 1800, "items": items}
    r = await client.put(f"/api/v1/workouts/{id_}", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return r.json()


def plank(*seconds: int) -> dict:
    return {"exercise_name": "Plank", "sets": [{"reps": 0, "weight": 0, "duration_seconds": s} for s in seconds]}


def run(*sets: tuple[float, int]) -> dict:
    return {
        "exercise_name": "Running",
        "sets": [{"reps": 0, "weight": 0, "distance_m": m, "duration_seconds": s} for m, s in sets],
    }


async def test_timed_and_cardio_sets_round_trip(client, user):
    w = await put_workout(client, user["headers"], 1, [plank(60, 75), run((5000, 1500))])
    plank_sets, run_sets = (item["sets"] for item in w["items"])
    assert [(s["reps"], s["duration_seconds"], s["distance_m"]) for s in plank_sets] == [(0, 60, None), (0, 75, None)]
    assert [(s["distance_m"], s["duration_seconds"]) for s in run_sets] == [(5000, 1500)]


@pytest.mark.parametrize(
    "bad",
    [{"duration_seconds": -1}, {"duration_seconds": 25 * 3600}, {"distance_m": -5}, {"distance_m": 2_000_000}],
    ids=["negative-time", "over-a-day", "negative-distance", "too-far"],
)
async def test_validation(client, user, bad):
    body = {
        "performed_at": "2026-11-01T08:00:00Z",
        "items": [{"exercise_name": "Plank", "sets": [{"reps": 0, "weight": 0, **bad}]}],
    }
    r = await client.put(f"/api/v1/workouts/{uuid.uuid4()}", json=body, headers=user["headers"])
    assert r.status_code == 422


async def test_records_longest_hold_and_farthest_distance(client, user):
    h = user["headers"]
    await put_workout(client, h, 1, [plank(60), run((5000, 1500))])  # the first time only sets the bar
    w = await put_workout(client, h, 3, [plank(50, 90), run((4000, 1100), (6000, 2100))])
    plank_sets, run_sets = (item["sets"] for item in w["items"])
    assert [s["pr"] for s in plank_sets] == [[], ["duration"]]
    # A shorter run, however fast, is no record; a longer one is (its time is not a record by itself).
    assert [s["pr"] for s in run_sets] == [[], ["distance"]]

    exercises = {e["name"]: e for e in (await client.get("/api/v1/exercises/", headers=h)).json()}
    assert exercises["Plank"]["best_duration"]["duration_seconds"] == 90
    assert exercises["Plank"]["best_distance"] is None
    assert exercises["Plank"]["best_weight"] is None and exercises["Plank"]["best_reps"] is None
    assert exercises["Running"]["best_distance"]["distance_m"] == 6000
    assert exercises["Running"]["best_duration"] is None  # every run has a distance
    assert exercises["Running"]["last_sets"][1]["distance_m"] == 6000


async def test_timed_sets_earn_xp_like_any_working_set(client, user):
    h = user["headers"]
    await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": "Plank", "muscle_group": "core"}, headers=h)
    await put_workout(client, h, 2, [plank(60, 60, 60)])
    p = (await client.get("/api/v1/progress", params={"tz": "UTC"}, headers=h)).json()
    values = {a["id"]: a["value"] for a in p["achievements"]}
    assert values["sets"] == 3
    assert values["muscle_core"] == 3
    workout_xp = RULES["workout"] + 3 * RULES["working_set"]
    tier_xp = sum(t["xp"] for a in p["achievements"] for t in a["tiers"] if t["unlocked_at"])
    assert p["xp"] == workout_xp + tier_xp


async def test_an_exercise_keeps_what_its_sets_are(client, user):
    h = user["headers"]
    id_ = str(uuid.uuid4())
    r = await client.put(
        f"/api/v1/exercises/{id_}", json={"name": "Rowing Machine", "muscle_group": "cardio", "log_type": "cardio"}, headers=h
    )
    assert r.status_code == 201, r.text
    assert (r.json()["log_type"], r.json()["muscle_group"]) == ("cardio", "cardio")
    r = await client.put(f"/api/v1/exercises/{id_}", json={"name": "Rowing Machine", "log_type": "sprints"}, headers=h)
    assert r.status_code == 422
    r = await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": "Squat"}, headers=h)
    assert r.json()["log_type"] is None  # not set: the library's, else weight × reps


async def test_backup_keeps_times_distances_and_log_types(client, user, make_user):
    h = user["headers"]
    await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": "Plank", "log_type": "time"}, headers=h)
    await put_workout(client, h, 1, [plank(45), run((3000, 1000))])
    backup = (await client.get("/api/v1/export", headers=h)).json()

    other = await make_user(email="kyle@example.com")
    r = await client.post("/api/v1/import", json=backup, headers=other["headers"])
    assert r.status_code == 200, r.text
    exercises = {e["name"]: e for e in (await client.get("/api/v1/exercises/", headers=other["headers"])).json()}
    assert exercises["Plank"]["log_type"] == "time"
    w = (await client.get("/api/v1/workouts/", headers=other["headers"])).json()[0]
    assert w["items"][0]["sets"][0]["duration_seconds"] == 45
    assert (w["items"][1]["sets"][0]["distance_m"], w["items"][1]["sets"][0]["duration_seconds"]) == (3000, 1000)
