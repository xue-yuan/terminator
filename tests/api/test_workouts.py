import uuid

import pytest

pytestmark = pytest.mark.anyio


def workout(**overrides) -> dict:
    return {
        "name": "Push",
        "performed_at": "2026-11-10T08:30:00+08:00",
        "duration_seconds": 3600,
        "notes": "felt strong",
        "items": [
            {
                "exercise_name": "Bench Press",
                "sets": [
                    {"reps": 5, "weight": 100, "rpe": 8},
                    {"reps": 5, "weight": 102.5, "rpe": 9},
                ],
            },
            {"exercise_name": "  Dips  ", "sets": [{"reps": 12, "weight": 0}]},
        ],
    } | overrides


async def test_create_and_read_back(client, user):
    r = await client.post("/api/v1/workouts/", json=workout(), headers=user["headers"])
    assert r.status_code == 201, r.text
    body = r.json()
    uuid.UUID(body["id"])
    assert body["performed_at"] == "2026-11-10T00:30:00Z"
    assert [i["exercise_name"] for i in body["items"]] == ["Bench Press", "Dips"]
    assert [s["weight"] for s in body["items"][0]["sets"]] == [100, 102.5]
    assert body["items"][1]["sets"] == [
        {"reps": 12, "weight": 0, "rpe": None, "kind": "working", "duration_seconds": None, "distance_m": None, "pr": []}
    ]

    r = await client.get(f"/api/v1/workouts/{body['id']}", headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["items"] == body["items"]


async def test_naive_datetime_is_rejected(client, user):
    r = await client.post(
        "/api/v1/workouts/", json=workout(performed_at="2026-11-10T08:30:00"), headers=user["headers"]
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    "bad",
    [
        {"items": [{"exercise_name": "", "sets": []}]},
        {"items": [{"exercise_name": "Squat", "sets": [{"reps": -1, "weight": 100}]}]},
        {"items": [{"exercise_name": "Squat", "sets": [{"reps": 5, "weight": 100, "rpe": 11}]}]},
    ],
    ids=["empty-name", "negative-reps", "rpe-out-of-range"],
)
async def test_validation(client, user, bad):
    r = await client.post("/api/v1/workouts/", json=workout(**bad), headers=user["headers"])
    assert r.status_code == 422


async def test_list_is_newest_first_and_scoped_to_user(client, user, make_user):
    other = await make_user(email="t800@example.com")
    for day in (3, 12, 7):
        await client.post(
            "/api/v1/workouts/",
            json=workout(name=f"d{day}", performed_at=f"2026-11-{day:02d}T10:00:00Z"),
            headers=user["headers"],
        )
    await client.post("/api/v1/workouts/", json=workout(name="theirs"), headers=other["headers"])

    r = await client.get("/api/v1/workouts/", headers=user["headers"])
    assert [w["name"] for w in r.json()] == ["d12", "d7", "d3"]
    r = await client.get("/api/v1/workouts/?limit=1&skip=1", headers=user["headers"])
    assert [w["name"] for w in r.json()] == ["d7"]


async def test_put_is_an_idempotent_upsert(client, user):
    wid = str(uuid.uuid4())
    url = f"/api/v1/workouts/{wid}"

    first = await client.put(url, json=workout(), headers=user["headers"])
    assert first.status_code == 201
    retry = await client.put(url, json=workout(), headers=user["headers"])
    assert retry.status_code == 200
    assert retry.json()["created_at"] == first.json()["created_at"]

    edited = workout(name="Push (edited)", items=[{"exercise_name": "OHP", "sets": [{"reps": 8, "weight": 50}]}])
    r = await client.put(url, json=edited, headers=user["headers"])
    assert r.status_code == 200
    assert r.json()["name"] == "Push (edited)"
    assert [i["exercise_name"] for i in r.json()["items"]] == ["OHP"]
    assert r.json()["updated_at"] > first.json()["updated_at"]

    listed = (await client.get("/api/v1/workouts/", headers=user["headers"])).json()
    assert len(listed) == 1


async def test_post_with_existing_id_conflicts(client, user):
    wid = str(uuid.uuid4())
    await client.put(f"/api/v1/workouts/{wid}", json=workout(), headers=user["headers"])
    r = await client.post("/api/v1/workouts/", json=workout(id=wid), headers=user["headers"])
    assert r.status_code == 409


async def test_other_users_workouts_are_invisible(client, user, make_user):
    other = await make_user(email="t800@example.com")
    wid = (await client.post("/api/v1/workouts/", json=workout(), headers=user["headers"])).json()["id"]
    url = f"/api/v1/workouts/{wid}"

    assert (await client.get(url, headers=other["headers"])).status_code == 404
    assert (await client.put(url, json=workout(name="hijack"), headers=other["headers"])).status_code == 404
    assert (await client.delete(url, headers=other["headers"])).status_code == 204  # no-op
    assert (await client.get(url, headers=user["headers"])).json()["name"] == "Push"


async def test_delete_is_idempotent(client, user):
    wid = (await client.post("/api/v1/workouts/", json=workout(), headers=user["headers"])).json()["id"]
    url = f"/api/v1/workouts/{wid}"
    assert (await client.delete(url, headers=user["headers"])).status_code == 204
    assert (await client.delete(url, headers=user["headers"])).status_code == 204
    assert (await client.get(url, headers=user["headers"])).status_code == 404


async def test_exercise_list_after_workouts(client, user):
    await client.post(
        "/api/v1/workouts/",
        json=workout(performed_at="2026-11-01T10:00:00Z"),
        headers=user["headers"],
    )
    await client.post(
        "/api/v1/workouts/",
        json=workout(
            performed_at="2026-11-08T10:00:00Z",
            items=[
                {"exercise_name": "bench press", "sets": [{"reps": 3, "weight": 110}]},
                {"exercise_name": "Plank", "sets": []},  # no sets: listed, but never performed
            ],
        ),
        headers=user["headers"],
    )
    r = await client.get("/api/v1/exercises/", headers=user["headers"])
    assert r.status_code == 200
    by_name = {e["name"]: e for e in r.json()}
    assert set(by_name) == {"Bench Press", "Dips", "Plank"}
    bench = by_name["Bench Press"]
    assert bench["times_performed"] == 2
    assert bench["last_performed_at"] == "2026-11-08T10:00:00Z"
    assert bench["last_sets"] == [{"reps": 3, "weight": 110, "rpe": None, "kind": "working", "duration_seconds": None, "distance_m": None}]
    assert by_name["Plank"]["times_performed"] == 0


async def test_activity_lists_every_workout_in_brief(client, user, make_user):
    h = user["headers"]
    url = "/api/v1/workouts/activity"
    assert (await client.get(url, headers=h)).json() == []

    older = workout(
        performed_at="2026-11-01T10:00:00Z",
        items=[
            {
                "exercise_name": "Squat",
                "sets": [
                    {"reps": 5, "weight": 60, "kind": "warmup"},
                    {"reps": 5, "weight": 100},
                    {"reps": 5, "weight": 100},
                    {"reps": 0, "weight": 100},  # 0 reps (older builds allowed it): not a set
                ],
            },
            {"exercise_name": "Plank", "sets": []},
        ],
    )
    first = (await client.post("/api/v1/workouts/", json=older, headers=h)).json()
    empty = (
        await client.post(
            "/api/v1/workouts/",
            json=workout(name=None, performed_at="2026-11-03T10:00:00Z", duration_seconds=None, items=[]),
            headers=h,
        )
    ).json()
    latest = (await client.post("/api/v1/workouts/", json=workout(), headers=h)).json()
    # Someone else's workouts are not yours.
    other = await make_user(email="t1000@example.com")
    await client.post("/api/v1/workouts/", json=workout(), headers=other["headers"])

    r = await client.get(url, headers=h)
    assert r.status_code == 200, r.text
    def brief(w, at, name="Push", duration=3600, sets=0):
        return {"id": w["id"], "performed_at": at, "name": name, "duration_seconds": duration, "sets": sets}

    assert r.json() == [  # most recent first; warm-ups and empty exercises add no sets
        brief(latest, "2026-11-10T00:30:00Z", sets=3),
        brief(empty, "2026-11-03T10:00:00Z", name=None, duration=None),
        brief(first, "2026-11-01T10:00:00Z", sets=2),
    ]

    # An edit shows up; a deleted workout is gone.
    await client.put(f"/api/v1/workouts/{first['id']}", json=older | {"items": older["items"][:1] * 2}, headers=h)
    await client.delete(f"/api/v1/workouts/{empty['id']}", headers=h)
    assert [(a["id"], a["sets"]) for a in (await client.get(url, headers=h)).json()] == [
        (latest["id"], 3),
        (first["id"], 4),
    ]

    assert (await client.get(url)).status_code == 401
