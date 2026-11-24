import uuid

import pytest

pytestmark = pytest.mark.anyio


def workout(performed_at: str, *items: dict, **overrides) -> dict:
    return {"name": "W", "performed_at": performed_at, "items": list(items)} | overrides


def item(name: str, *sets: tuple, unit: str | None = None, superset: int | None = None) -> dict:
    body = {"exercise_name": name, "sets": [{"weight": w, "reps": r} for w, r in sets]}
    if unit:
        body["weight_unit"] = unit
    if superset is not None:
        body["superset"] = superset
    return body


async def put(client, user, body: dict) -> dict:
    r = await client.put(f"/api/v1/workouts/{uuid.uuid4()}", json=body, headers=user["headers"])
    assert r.status_code == 201, r.text
    return r.json()


async def test_weight_unit_and_superset_round_trip(client, user):
    body = await put(
        client,
        user,
        workout(
            "2026-11-10T08:00:00Z",
            item("Leg Press", (90, 10), unit="lb", superset=1),
            item("Leg Curl", (40, 12), superset=1),
            item("Plank", (0, 60)),
        ),
    )
    assert [(i["weight_unit"], i["superset"]) for i in body["items"]] == [("lb", 1), ("kg", 1), ("kg", None)]
    # stored as entered: no conversion
    assert body["items"][0]["sets"][0]["weight"] == 90


@pytest.mark.parametrize("bad", [{"weight_unit": "stone"}, {"superset": 0}], ids=["unit", "superset"])
async def test_item_validation(client, user, bad):
    body = workout("2026-11-10T08:00:00Z", item("Squat", (100, 5)) | bad)
    r = await client.put(f"/api/v1/workouts/{uuid.uuid4()}", json=body, headers=user["headers"])
    assert r.status_code == 422


async def exercises(client, user) -> dict[str, dict]:
    r = await client.get("/api/v1/exercises/", headers=user["headers"])
    assert r.status_code == 200, r.text
    return {e["name"]: e for e in r.json()}


async def test_items_resolve_to_one_exercise_ignoring_case(client, user):
    w1 = await put(client, user, workout("2026-11-01T08:00:00Z", item("Bench Press", (100, 5))))
    w2 = await put(client, user, workout("2026-11-08T08:00:00Z", item(" bench PRESS ", (102.5, 5))))
    assert w1["items"][0]["exercise_id"] == w2["items"][0]["exercise_id"]
    assert w2["items"][0]["exercise_name"] == "Bench Press"  # the exercise's name, not the spelling sent
    ex = await exercises(client, user)
    assert list(ex) == ["Bench Press"]
    assert ex["Bench Press"]["times_performed"] == 2


async def test_new_exercise_keeps_the_client_id_and_unknown_ids_fall_back_to_the_name(client, user):
    fly = str(uuid.uuid4())
    body = await put(client, user, workout("2026-11-01T08:00:00Z", item("Cable Fly", (15, 12)) | {"exercise_id": fly}))
    assert body["items"][0]["exercise_id"] == fly
    # another device created "cable fly" offline under its own id: lands on the same exercise
    other_device = str(uuid.uuid4())
    body = await put(client, user, workout("2026-11-02T08:00:00Z", item("cable fly", (17.5, 10)) | {"exercise_id": other_device}))
    assert body["items"][0]["exercise_id"] == fly
    r = await client.get(f"/api/v1/exercises/{other_device}", headers=user["headers"])
    assert r.status_code == 404


async def test_list_reports_last_sets_and_records_compared_in_kg(client, user):
    await put(client, user, workout("2026-11-01T08:00:00Z", item("Bench Press", (100, 8), (60, 15))))
    await put(client, user, workout("2026-11-08T08:00:00Z", item("Bench Press", (225, 5), unit="lb")))
    # Dips with more reps weighted than bodyweight: the reps record is the bodyweight one.
    await put(client, user, workout("2026-11-09T08:00:00Z", item("Dips", (0, 12), (0, 15), (20, 20))))
    ex = await exercises(client, user)
    bench = ex["Bench Press"]
    assert (bench["last_unit"], bench["last_sets"]) == ("lb", [{"weight": 225, "reps": 5, "rpe": None, "kind": "working", "duration_seconds": None, "distance_m": None}])
    # 225 lb = 102.1 kg beats 100 kg
    assert (bench["best_weight"]["weight"], bench["best_weight"]["weight_unit"]) == (225, "lb")
    # 100 kg x 8 (est. 126.7 kg) beats 225 lb x 5 (est. 119.1 kg); 60 x 15 is past the 12-rep cutoff
    assert (bench["best_e1rm"]["weight"], bench["best_e1rm"]["reps"]) == (100, 8)
    assert bench["best_reps"] is None  # most reps is a bodyweight record
    dips = ex["Dips"]
    assert (dips["best_weight"]["weight"], dips["best_weight"]["reps"]) == (20, 20)
    assert dips["best_e1rm"] is None  # 20 reps is past the cutoff
    assert (dips["best_reps"]["weight"], dips["best_reps"]["reps"]) == (0, 15)


async def test_warmup_sets_round_trip_and_never_count_as_records(client, user):
    warmup = {"weight": 140, "reps": 8, "kind": "warmup"}  # heavier than any working set: ignored
    body = await put(
        client,
        user,
        workout(
            "2026-11-01T08:00:00Z",
            {"exercise_name": "Squat", "sets": [warmup, {"weight": 100, "reps": 5}, {"weight": 100, "reps": 4}]},
        ),
    )
    assert [s["kind"] for s in body["items"][0]["sets"]] == ["warmup", "working", "working"]
    squat = (await exercises(client, user))["Squat"]
    assert (squat["best_weight"]["weight"], squat["best_weight"]["reps"]) == (100, 5)
    assert squat["best_reps"] is None  # no bodyweight sets
    assert [s["kind"] for s in squat["last_sets"]] == ["warmup", "working", "working"]  # hints need both

    r = await client.put(
        f"/api/v1/workouts/{uuid.uuid4()}",
        json=workout("2026-11-02T08:00:00Z", {"exercise_name": "Squat", "sets": [{"weight": 1, "reps": 1, "kind": "drop"}]}),
        headers=user["headers"],
    )
    assert r.status_code == 422


async def test_progress_is_oldest_first_and_scoped(client, user, make_user):
    other = await make_user(email="t1000@example.com")
    theirs = await put(client, other, workout("2026-11-05T08:00:00Z", item("Bench Press", (300, 1))))
    w2 = await put(client, user, workout("2026-11-09T08:00:00Z", item("bench press", (225, 5), unit="lb")))
    w1 = await put(client, user, workout("2026-11-02T08:00:00Z", item("Bench Press", (100, 5), (102.5, 3))))
    await put(client, user, workout("2026-11-04T08:00:00Z", item("Bench Press")))  # no sets: ignored
    bench_id = w1["items"][0]["exercise_id"]

    r = await client.get(f"/api/v1/exercises/{bench_id}/progress", headers=user["headers"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exercise_name"] == "bench press"  # created by the first upload
    assert [s["workout_id"] for s in body["sessions"]] == [w1["id"], w2["id"]]
    assert [s["weight_unit"] for s in body["sessions"]] == ["kg", "lb"]
    assert body["sessions"][0]["sets"] == [
        {"weight": 100, "reps": 5, "rpe": None, "kind": "working", "duration_seconds": None, "distance_m": None},
        {"weight": 102.5, "reps": 3, "rpe": None, "kind": "working", "duration_seconds": None, "distance_m": None},
    ]
    theirs_id = theirs["items"][0]["exercise_id"]
    r = await client.get(f"/api/v1/exercises/{theirs_id}/progress", headers=user["headers"])
    assert r.status_code == 404


async def test_rename_updates_workouts_and_plans(client, user):
    w = await put(client, user, workout("2026-11-02T08:00:00Z", item("臥推", (60, 8))))
    bench_id = w["items"][0]["exercise_id"]
    r = await client.post(
        "/api/v1/plans/",
        json={"name": "P", "days": [{"name": "D", "exercises": [{"exercise_name": "臥推"}]}]},
        headers=user["headers"],
    )
    plan_id = r.json()["id"]
    assert r.json()["days"][0]["exercises"][0]["exercise_id"] == bench_id

    r = await client.put(
        f"/api/v1/exercises/{bench_id}",
        json={"name": "Bench Press", "muscle_group": "chest", "notes": "Bench at notch 3", "rep_min": 6, "rep_max": 10},
        headers=user["headers"],
    )
    assert r.status_code == 200, r.text
    assert (r.json()["name"], r.json()["notes"], r.json()["times_performed"]) == ("Bench Press", "Bench at notch 3", 1)

    r = await client.get(f"/api/v1/workouts/{w['id']}", headers=user["headers"])
    assert r.json()["items"][0]["exercise_name"] == "Bench Press"
    assert r.json()["updated_at"] > w["updated_at"]  # clients refresh their cached copy
    r = await client.get(f"/api/v1/plans/{plan_id}", headers=user["headers"])
    assert r.json()["days"][0]["exercises"][0]["exercise_name"] == "Bench Press"


async def test_create_exercise_and_name_conflicts(client, user):
    squat = str(uuid.uuid4())
    r = await client.put(f"/api/v1/exercises/{squat}", json={"name": "Squat"}, headers=user["headers"])
    assert r.status_code == 201
    r = await client.put(f"/api/v1/exercises/{squat}", json={"name": "Squat", "increment": 5}, headers=user["headers"])
    assert (r.status_code, r.json()["increment"]) == (200, 5)

    r = await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": "SQUAT"}, headers=user["headers"])
    assert r.status_code == 409
    assert r.json()["detail"]["existing_id"] == squat

    bad = {"name": "X", "rep_min": 12, "rep_max": 8}
    r = await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json=bad, headers=user["headers"])
    assert r.status_code == 422


async def test_merge_moves_history_and_plan_entries(client, user, make_user):
    w1 = await put(client, user, workout("2026-11-02T08:00:00Z", item("臥推", (60, 8)), item("Squat", (100, 5))))
    w2 = await put(client, user, workout("2026-11-09T08:00:00Z", item("Bench Press", (65, 8))))
    zh_id, bench_id = w1["items"][0]["exercise_id"], w2["items"][0]["exercise_id"]
    await client.put(f"/api/v1/exercises/{zh_id}", json={"name": "臥推", "notes": "notch 3"}, headers=user["headers"])
    r = await client.post(
        "/api/v1/plans/",
        json={"name": "P", "days": [{"name": "D", "exercises": [{"exercise_name": "臥推"}]}]},
        headers=user["headers"],
    )
    plan_id = r.json()["id"]

    # both in one workout too: still counts as one time performed
    w3 = await put(client, user, workout("2026-11-10T08:00:00Z", item("臥推", (60, 8)), item("Bench Press", (70, 5))))
    r = await client.post(f"/api/v1/exercises/{zh_id}/merge", json={"into": bench_id}, headers=user["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {"workouts": 2, "plan_exercises": 1}

    ex = await exercises(client, user)
    assert set(ex) == {"Bench Press", "Squat"}
    assert ex["Bench Press"]["times_performed"] == 3  # w1, w2, w3
    r = await client.get(f"/api/v1/workouts/{w3['id']}", headers=user["headers"])
    assert [i["exercise_id"] for i in r.json()["items"]] == [bench_id, bench_id]
    assert ex["Bench Press"]["notes"] == "notch 3"  # taken over: the target had none
    r = await client.get(f"/api/v1/workouts/{w1['id']}", headers=user["headers"])
    assert [i["exercise_name"] for i in r.json()["items"]] == ["Bench Press", "Squat"]
    r = await client.get(f"/api/v1/plans/{plan_id}", headers=user["headers"])
    assert r.json()["days"][0]["exercises"][0]["exercise_id"] == bench_id

    r = await client.post(f"/api/v1/exercises/{bench_id}/merge", json={"into": bench_id}, headers=user["headers"])
    assert r.status_code == 422
    other = await make_user(email="t1000@example.com")
    r = await client.post(f"/api/v1/exercises/{bench_id}/merge", json={"into": bench_id}, headers=other["headers"])
    assert r.status_code == 404


async def test_delete_only_unused_exercises(client, user):
    w = await put(client, user, workout("2026-11-02T08:00:00Z", item("Squat", (100, 5))))
    used = w["items"][0]["exercise_id"]
    assert (await client.delete(f"/api/v1/exercises/{used}", headers=user["headers"])).status_code == 409
    unused = str(uuid.uuid4())
    await client.put(f"/api/v1/exercises/{unused}", json={"name": "Typo"}, headers=user["headers"])
    assert (await client.delete(f"/api/v1/exercises/{unused}", headers=user["headers"])).status_code == 204
    assert (await client.delete(f"/api/v1/exercises/{unused}", headers=user["headers"])).status_code == 204
    assert set(await exercises(client, user)) == {"Squat"}


async def test_plan_superset_round_trip(client, user):
    exercises = [
        {"exercise_name": "Curl", "superset": 1},
        {"exercise_name": "Pushdown", "superset": 1},
        {"exercise_name": "Plank"},
    ]
    r = await client.post(
        "/api/v1/plans/", json={"name": "Arms", "days": [{"name": "A", "exercises": exercises}]}, headers=user["headers"]
    )
    assert r.status_code == 201, r.text
    assert [e["superset"] for e in r.json()["days"][0]["exercises"]] == [1, 1, None]
