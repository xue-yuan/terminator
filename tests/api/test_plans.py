from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.anyio


def plan(**overrides) -> dict:
    return {
        "name": "Upper / Lower",
        "description": "4 days a week",
        "days": [
            {
                "name": "Upper A",
                "exercises": [
                    {"exercise_name": "Bench Press", "target_sets": 4, "target_reps_min": 5, "target_reps_max": 8},
                    {"exercise_name": "Row", "target_sets": 3},
                ],
            },
            {"name": "Lower A", "exercises": [{"exercise_name": "Squat", "target_sets": 5, "target_reps_min": 5, "target_reps_max": 5}]},
        ],
    } | overrides


async def _create(client, headers, **overrides) -> dict:
    r = await client.post("/api/v1/plans/", json=plan(**overrides), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_and_list(client, user):
    created = await _create(client, user["headers"])
    assert [d["name"] for d in created["days"]] == ["Upper A", "Lower A"]
    assert [e["exercise_name"] for e in created["days"][0]["exercises"]] == ["Bench Press", "Row"]
    assert created["is_active"] is False

    listed = (await client.get("/api/v1/plans/", headers=user["headers"])).json()
    assert [p["id"] for p in listed] == [created["id"]]


async def test_reps_range_validation(client, user):
    bad = plan(days=[{"name": "D", "exercises": [{"exercise_name": "X", "target_reps_min": 10, "target_reps_max": 5}]}])
    r = await client.post("/api/v1/plans/", json=bad, headers=user["headers"])
    assert r.status_code == 422


async def test_update_keeps_day_ids_by_position(client, user):
    created = await _create(client, user["headers"])
    day_ids = [d["id"] for d in created["days"]]

    updated = plan(
        name="Renamed",
        days=[
            {"name": "Upper A*", "exercises": [{"exercise_name": "Incline Bench"}]},
            {"name": "Lower A", "exercises": []},
            {"name": "Upper B", "exercises": []},
        ],
    )
    r = await client.put(f"/api/v1/plans/{created['id']}", json=updated, headers=user["headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    assert [d["id"] for d in body["days"]][:2] == day_ids
    assert [d["name"] for d in body["days"]] == ["Upper A*", "Lower A", "Upper B"]
    assert body["days"][0]["exercises"][0]["exercise_name"] == "Incline Bench"

    r = await client.put(f"/api/v1/plans/{created['id']}", json=plan(days=[{"name": "Only"}]), headers=user["headers"])
    assert [d["id"] for d in r.json()["days"]] == day_ids[:1]


async def test_private_plans_of_others_are_hidden(client, user, make_user):
    other = await make_user(email="t800@example.com")
    theirs = await _create(client, other["headers"])
    url = f"/api/v1/plans/{theirs['id']}"
    assert (await client.get(url, headers=user["headers"])).status_code == 404
    assert (await client.post(f"{url}/activate", headers=user["headers"])).status_code == 404
    assert (await client.put(url, json=plan(), headers=user["headers"])).status_code == 404
    assert (await client.delete(url, headers=user["headers"])).status_code == 404

    # A workout can't reference a day of someone else's private plan
    w = {"performed_at": "2026-11-10T10:00:00Z", "plan_day_id": theirs["days"][0]["id"], "items": []}
    assert (await client.post("/api/v1/workouts/", json=w, headers=user["headers"])).status_code == 422


async def test_public_plans_can_be_followed_but_not_edited(client, user, make_user):
    other = await make_user(email="t800@example.com")
    theirs = await _create(client, other["headers"], is_public=True)
    url = f"/api/v1/plans/{theirs['id']}"
    assert (await client.get(url, headers=user["headers"])).status_code == 200
    assert (await client.post(f"{url}/activate", headers=user["headers"])).json()["is_active"] is True
    assert (await client.put(url, json=plan(), headers=user["headers"])).status_code == 404


async def test_activate_summary_and_next_day(client, user):
    p = await _create(client, user["headers"])
    upper, lower = (d["id"] for d in p["days"])

    r = await client.post(f"/api/v1/plans/{p['id']}/activate", headers=user["headers"])
    assert r.json()["is_active"] is True
    listed = (await client.get("/api/v1/plans/", headers=user["headers"])).json()
    assert listed[0]["is_active"] is True

    summary = (await client.get("/api/v1/users/me/summary", headers=user["headers"])).json()
    assert summary["active_plan"]["id"] == p["id"]
    assert summary["next_plan_day_id"] == upper

    now = datetime.now(timezone.utc)
    for offset, day in ((2, upper), (1, lower)):
        w = {"performed_at": (now - timedelta(minutes=offset)).isoformat(), "plan_day_id": day, "items": []}
        assert (await client.post("/api/v1/workouts/", json=w, headers=user["headers"])).status_code == 201
    summary = (await client.get("/api/v1/users/me/summary", headers=user["headers"])).json()
    assert summary["next_plan_day_id"] == upper  # wraps around after the last day

    assert (await client.post("/api/v1/plans/deactivate", headers=user["headers"])).status_code == 204
    summary = (await client.get("/api/v1/users/me/summary", headers=user["headers"])).json()
    assert summary["active_plan"] is None


async def test_deleting_active_plan_clears_it_and_keeps_workouts(client, user):
    p = await _create(client, user["headers"])
    await client.post(f"/api/v1/plans/{p['id']}/activate", headers=user["headers"])
    w = {"performed_at": "2026-11-10T10:00:00Z", "plan_day_id": p["days"][0]["id"], "items": []}
    wid = (await client.post("/api/v1/workouts/", json=w, headers=user["headers"])).json()["id"]

    assert (await client.delete(f"/api/v1/plans/{p['id']}", headers=user["headers"])).status_code == 204
    summary = (await client.get("/api/v1/users/me/summary", headers=user["headers"])).json()
    assert summary["active_plan"] is None
    kept = (await client.get(f"/api/v1/workouts/{wid}", headers=user["headers"])).json()
    assert kept["plan_day_id"] is None
