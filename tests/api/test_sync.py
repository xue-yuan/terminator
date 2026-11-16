import uuid

import pytest

pytestmark = pytest.mark.anyio

URL = "/api/v1/sync/state"


def workout(**overrides) -> dict:
    return {
        "performed_at": "2026-11-10T08:00:00Z",
        "items": [{"exercise_name": "Squat", "weight_unit": "kg", "sets": [{"weight": 100, "reps": 5}]}],
    } | overrides


async def _state(client, user) -> dict:
    r = await client.get(URL, headers=user["headers"])
    assert r.status_code == 200, r.text
    return r.json()


def changed(before: dict, after: dict) -> set[str]:
    return {k for k in after if after[k] != before[k]}


async def test_fingerprints_move_only_with_their_data(client, user, make_user):
    s0 = await _state(client, user)
    assert set(s0) == {"workouts", "exercises", "plans", "body_weights", "summary", "spotify", "user"}
    assert s0 == await _state(client, user)  # stable while nothing changes

    # A workout (which creates its exercise) moves what shows workouts or their stats.
    wid = uuid.uuid4()
    assert (await client.put(f"/api/v1/workouts/{wid}", json=workout(), headers=user["headers"])).status_code == 201
    s1 = await _state(client, user)
    assert changed(s0, s1) == {"workouts", "exercises", "plans", "summary"}

    # Editing it again moves them again (same row count, later update).
    await client.put(f"/api/v1/workouts/{wid}", json=workout(notes="felt heavy"), headers=user["headers"])
    s2 = await _state(client, user)
    assert {"workouts", "summary"} <= changed(s1, s2)

    # A weigh-in only moves body weights.
    entry = {"measured_at": "2026-11-10T07:00:00Z", "weight": 80, "unit": "kg"}
    await client.put(f"/api/v1/body-weights/{uuid.uuid4()}", json=entry, headers=user["headers"])
    s3 = await _state(client, user)
    assert changed(s2, s3) == {"body_weights"}

    # Plans: creating one, then renaming it, then editing a day's exercises in place.
    body = {"name": "PPL", "days": [{"name": "Push", "exercises": [{"exercise_name": "Squat"}]}]}
    plan = (await client.post("/api/v1/plans/", json=body, headers=user["headers"])).json()
    s4 = await _state(client, user)
    assert changed(s3, s4) == {"plans", "summary"}
    await client.put(f"/api/v1/plans/{plan['id']}", json=body | {"name": "Push Pull Legs"}, headers=user["headers"])
    s5 = await _state(client, user)
    assert "plans" in changed(s4, s5)
    body["days"][0]["exercises"][0]["target_sets"] = 5
    await client.put(f"/api/v1/plans/{plan['id']}", json=body | {"name": "Push Pull Legs"}, headers=user["headers"])
    s6 = await _state(client, user)
    assert "plans" in changed(s5, s6)

    # Following a plan moves the summary (it shows the next day) and the user.
    await client.post(f"/api/v1/plans/{plan['id']}/activate", headers=user["headers"])
    s7 = await _state(client, user)
    assert changed(s6, s7) == {"summary", "user"}

    # Deleting the workout moves it back out.
    await client.delete(f"/api/v1/workouts/{wid}", headers=user["headers"])
    assert "workouts" in changed(s7, await _state(client, user))

    # Someone else's changes don't touch yours.
    other = await make_user(email="t1000@example.com")
    before = await _state(client, user)
    await client.put(f"/api/v1/workouts/{uuid.uuid4()}", json=workout(), headers=other["headers"])
    assert before == await _state(client, user)


async def test_needs_sign_in(client):
    assert (await client.get(URL)).status_code == 401
