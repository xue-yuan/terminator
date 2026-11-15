import uuid

import pytest

pytestmark = pytest.mark.anyio


async def seed(client, user) -> None:
    h = user["headers"]
    squat = str(uuid.uuid4())
    await client.put(
        f"/api/v1/exercises/{squat}",
        json={"name": "Squat", "muscle_group": "legs", "notes": "belt", "rep_min": 5, "rep_max": 8, "increment": 5},
        headers=h,
    )
    for day, weight in ((1, 100), (8, 105)):
        body = {
            "name": "Legs",
            "performed_at": f"2026-11-{day:02d}T08:00:00Z",
            "duration_seconds": 3600,
            "items": [
                {
                    "exercise_id": squat,
                    "exercise_name": "Squat",
                    "superset": 1,
                    "sets": [{"weight": 60, "reps": 5, "kind": "warmup"}, {"weight": weight, "reps": 5, "rpe": 8}],
                },
                {"exercise_name": "Leg Curl", "weight_unit": "lb", "superset": 1, "sets": [{"weight": 90, "reps": 12}]},
            ],
        }
        await client.put(f"/api/v1/workouts/{uuid.uuid4()}", json=body, headers=h)
    plan = {"name": "Legs", "days": [{"name": "A", "exercises": [{"exercise_name": "Squat", "target_sets": 3}]}]}
    await client.post("/api/v1/plans/", json=plan, headers=h)
    entry = {"measured_at": "2026-11-02T07:00:00Z", "weight": 80, "unit": "kg"}
    await client.put(f"/api/v1/body-weights/{uuid.uuid4()}", json=entry, headers=h)


def shape(backup: dict) -> dict:
    """What should survive a round trip, without ids and timestamps."""
    return {
        "exercises": sorted((e["name"], e["muscle_group"], e["notes"], e["increment"]) for e in backup["exercises"]),
        "workouts": sorted(
            (
                w["performed_at"],
                w["name"],
                tuple(
                    (i["exercise_name"], i["weight_unit"], i["superset"], tuple((s["weight"], s["reps"], s["kind"], s["rpe"]) for s in i["sets"]))
                    for i in w["items"]
                ),
            )
            for w in backup["workouts"]
        ),
        "plans": [(p["name"], [[e["exercise_name"] for e in d["exercises"]] for d in p["days"]]) for p in backup["plans"]],
        "body_weights": [(b["measured_at"], b["weight"], b["unit"]) for b in backup["body_weights"]],
    }


async def test_backup_restores_into_another_account_and_reimport_updates(client, user, make_user):
    await seed(client, user)
    backup = (await client.get("/api/v1/export", headers=user["headers"])).json()
    assert backup["format"] == "terminator-backup" and len(backup["workouts"]) == 2

    other = await make_user(email="t1000@example.com")
    r = await client.post("/api/v1/import", json=backup, headers=other["headers"])
    assert r.status_code == 200, r.text
    assert r.json() == {
        "exercises_created": 2,
        "workouts_created": 2,
        "workouts_updated": 0,
        "plans_created": 1,
        "plans_skipped": 0,
        "body_weights": 1,
    }
    restored = (await client.get("/api/v1/export", headers=other["headers"])).json()
    assert shape(restored) == shape(backup)
    # their own copies: the original account is untouched
    assert {w["id"] for w in restored["workouts"]}.isdisjoint({w["id"] for w in backup["workouts"]})
    assert shape((await client.get("/api/v1/export", headers=user["headers"])).json()) == shape(backup)

    r = await client.post("/api/v1/import", json=backup, headers=other["headers"])
    assert r.json() == {
        "exercises_created": 0,
        "workouts_created": 0,
        "workouts_updated": 2,
        "plans_created": 0,
        "plans_skipped": 1,
        "body_weights": 1,
    }
    assert shape((await client.get("/api/v1/export", headers=other["headers"])).json()) == shape(backup)


async def test_import_key_makes_csv_imports_repeatable_and_names_match_exercises(client, user):
    await seed(client, user)
    converted = {
        "workouts": [
            {
                "import_key": "strong:2025-01-05 10:00:00:Push",
                "name": "Push",
                "performed_at": "2025-01-05T10:00:00+01:00",
                "items": [{"exercise_name": "squat", "sets": [{"weight": 90, "reps": 5}]}],
            }
        ]
    }
    first = (await client.post("/api/v1/import", json=converted, headers=user["headers"])).json()
    again = (await client.post("/api/v1/import", json=converted, headers=user["headers"])).json()
    assert (first["workouts_created"], again["workouts_created"], again["workouts_updated"]) == (1, 0, 1)
    exercises = (await client.get("/api/v1/exercises/", headers=user["headers"])).json()
    assert [e["name"] for e in exercises].count("Squat") == 1  # "squat" matched the existing one
    assert len((await client.get("/api/v1/workouts/", headers=user["headers"])).json()) == 3


async def test_import_validation(client, user):
    r = await client.post("/api/v1/import", json={"format": "something-else"}, headers=user["headers"])
    assert r.status_code == 422
    bad_set = {"workouts": [{"performed_at": "2025-01-05T10:00:00Z", "items": [{"exercise_name": "X", "sets": [{"weight": -1, "reps": 5}]}]}]}
    assert (await client.post("/api/v1/import", json=bad_set, headers=user["headers"])).status_code == 422
