import uuid

import pytest

pytestmark = pytest.mark.anyio


def sets(*specs) -> list[dict]:
    """(weight, reps) or (weight, reps, "warmup")"""
    return [{"weight": w, "reps": r, **({"kind": k[0]} if k else {})} for w, r, *k in specs]


async def log(client, user, day: int, *items, workout_id=None) -> dict:
    workout_id = workout_id or str(uuid.uuid4())
    body = {"performed_at": f"2026-11-{day:02d}T08:00:00Z", "items": list(items)}
    r = await client.put(f"/api/v1/workouts/{workout_id}", json=body, headers=user["headers"])
    assert r.status_code in (200, 201), r.text
    return r.json()


def flags(workout: dict, item: int = 0) -> list[list[str]]:
    return [s["pr"] for s in workout["items"][item]["sets"]]


def bench(*specs, unit="kg") -> dict:
    return {"exercise_name": "Bench Press", "weight_unit": unit, "sets": sets(*specs)}


async def test_prs_against_earlier_sets(client, user):
    first = await log(client, user, 1, bench((95, 5), (100, 5)))
    assert flags(first) == [[], []]  # nothing to beat in the first workout

    # heavier; then a better estimated 1RM (95 x 8 = 120.3 > 100 x 5 = 116.7); then a repeat
    w2 = await log(client, user, 2, bench((102.5, 3), (95, 8), (102.5, 3)))
    assert flags(w2) == [["weight"], ["e1rm"], []]

    # 230 lb = 104.3 kg beats 102.5 kg; a heavier warm-up is never a PR and doesn't raise the bar
    w3 = await log(client, user, 3, bench((150, 1, "warmup"), unit="kg"), bench((230, 1), unit="lb"))
    assert flags(w3, 0) == [[]]
    assert flags(w3, 1) == [["weight"]]
    w4 = await log(client, user, 4, bench((105, 1)))
    assert flags(w4) == [["weight"]]

    # read back the same way
    r = await client.get(f"/api/v1/workouts/{w2['id']}", headers=user["headers"])
    assert flags(r.json()) == [["weight"], ["e1rm"], []]


async def test_bodyweight_reps_prs(client, user):
    dips = lambda *specs: {"exercise_name": "Dips", "sets": sets(*specs)}  # noqa: E731
    await log(client, user, 1, dips((0, 10)))
    w2 = await log(client, user, 2, dips((0, 12), (0, 11)))
    assert flags(w2) == [["reps"], []]


async def test_prs_follow_changes_to_earlier_workouts(client, user):
    first_id = str(uuid.uuid4())
    await log(client, user, 1, bench((100, 5)), workout_id=first_id)
    w2 = await log(client, user, 2, bench((102.5, 5)))
    assert flags(w2) == [["weight", "e1rm"]]

    await log(client, user, 1, bench((110, 5)), workout_id=first_id)  # the earlier one was heavier after all
    r = await client.get("/api/v1/workouts/", headers=user["headers"])
    later = next(w for w in r.json() if w["id"] == w2["id"])
    assert flags(later) == [[]]
