"""A week's or month's training in review (GET /recap)."""

import uuid
from datetime import date

import pytest

from app.services.recap import period_bounds

pytestmark = pytest.mark.anyio

URL = "/api/v1/recap"


async def put_workout(client, h, at: str, items: list[dict], duration: int = 3600) -> str:
    id_ = str(uuid.uuid4())
    body = {"name": "W", "performed_at": at, "duration_seconds": duration, "items": items}
    r = await client.put(f"/api/v1/workouts/{id_}", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return id_


def bench(*sets: tuple[float, int], unit: str = "kg") -> dict:
    return {"exercise_name": "Bench Press", "weight_unit": unit, "sets": [{"weight": w, "reps": r} for w, r in sets]}


def test_period_bounds():
    # 2026-11-18 is a Wednesday.
    assert period_bounds("week", date(2026, 11, 18)) == (date(2026, 11, 16), date(2026, 11, 23), date(2026, 11, 9))
    assert period_bounds("month", date(2026, 11, 18)) == (date(2026, 11, 1), date(2026, 12, 1), date(2026, 10, 1))
    assert period_bounds("month", date(2027, 1, 31)) == (date(2027, 1, 1), date(2027, 2, 1), date(2026, 12, 1))


async def test_week_recap(client, user):
    h = user["headers"]
    await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": "Bench Press", "muscle_group": "chest"}, headers=h)
    await put_workout(client, h, "2026-11-10T09:00:00Z", [bench((100, 5), (100, 5))])  # the week before
    # Monday 01:00 in Taipei is still Sunday in UTC: it belongs to the week asked for, in Taipei.
    await put_workout(client, h, "2026-11-15T17:00:00Z", [bench((102.5, 5), (100, 5), (60, 10))], duration=3000)
    await put_workout(
        client,
        h,
        "2026-11-19T09:00:00Z",
        [
            bench((225, 3), unit="lb"),
            {"exercise_name": "Running", "sets": [{"weight": 0, "reps": 0, "distance_m": 5000, "duration_seconds": 1500}]},
            {"exercise_name": "Bench Press", "sets": [{"weight": 140, "reps": 1, "kind": "warmup"}]},
        ],
    )
    await put_workout(client, h, "2026-11-23T09:00:00Z", [bench((50, 5))])  # the week after

    r = await client.get(URL, params={"period": "week", "day": "2026-11-18", "tz": "Asia/Taipei"}, headers=h)
    assert r.status_code == 200, r.text
    recap = r.json()
    assert (recap["start"], recap["end"]) == ("2026-11-16", "2026-11-23")
    assert recap["days"] == ["2026-11-16", "2026-11-19"]
    t = recap["totals"]
    assert (t["workouts"], t["duration_seconds"], t["working_sets"]) == (2, 6600, 5)  # the warm-up doesn't count
    assert t["volume_kg"] == pytest.approx(102.5 * 5 + 100 * 5 + 60 * 10 + 225 * 0.45359237 * 3, abs=0.1)
    assert (t["distance_m"], t["cardio_seconds"]) == (5000, 1500)
    assert (recap["previous"]["workouts"], recap["previous"]["working_sets"]) == (1, 2)

    # 102.5 × 5 beats last week's 100 × 5. 225 lb × 3 (102.1 kg, est. 1RM 112.3) beats neither 102.5 kg
    # nor its est. 1RM of 119.6, and the first run only sets the bar.
    kinds = [(r["exercise_name"], r["weight"], r["kinds"]) for r in recap["records"]]
    assert kinds == [("Bench Press", 102.5, ["weight", "e1rm"])]
    assert recap["exercises"][0] | {"exercise_id": None} == {
        "exercise_id": None,
        "exercise_name": "Bench Press",
        "sets": 4,
        "volume_kg": pytest.approx(t["volume_kg"], abs=0.1),
    }
    assert recap["muscles"]["chest"] == 4
    assert recap["xp"] == 0  # nothing banked until GET /progress has run
    await client.get("/api/v1/progress", params={"tz": "Asia/Taipei"}, headers=h)
    recap = (await client.get(URL, params={"period": "week", "day": "2026-11-18", "tz": "Asia/Taipei"}, headers=h)).json()
    assert recap["xp"] > 0
    assert recap["unlocks"] == [] or all(u["title"] for u in recap["unlocks"])


async def test_month_recap_and_an_empty_one(client, user):
    h = user["headers"]
    await put_workout(client, h, "2026-10-31T09:00:00Z", [bench((80, 5))])
    await put_workout(client, h, "2026-11-01T09:00:00Z", [bench((85, 5))])
    recap = (await client.get(URL, params={"period": "month", "day": "2026-11-30"}, headers=h)).json()
    assert (recap["start"], recap["end"], recap["totals"]["workouts"], recap["previous"]["workouts"]) == (
        "2026-11-01",
        "2026-12-01",
        1,
        1,
    )
    empty = (await client.get(URL, params={"period": "month", "day": "2025-01-10"}, headers=h)).json()
    assert empty["totals"]["workouts"] == 0 and empty["records"] == [] and empty["days"] == []


async def test_recap_is_yours_only_and_checks_the_time_zone(client, user, make_user):
    await put_workout(client, user["headers"], "2026-11-19T09:00:00Z", [bench((100, 5))])
    other = await make_user(email="kyle@example.com")
    r = await client.get(URL, params={"period": "week", "day": "2026-11-19"}, headers=other["headers"])
    assert r.json()["totals"]["workouts"] == 0
    r = await client.get(URL, params={"period": "week", "day": "2026-11-19", "tz": "Mars/Olympus"}, headers=other["headers"])
    assert r.status_code == 422
    assert (await client.get(URL, params={"period": "year", "day": "2026-11-19"}, headers=other["headers"])).status_code == 422
