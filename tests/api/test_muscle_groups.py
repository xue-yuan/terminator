"""Muscle groups split later (arms into biceps and triceps; back, legs and shoulders
into muscles): the migrations and the API sort an exercise the same way."""

import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.catalog import CatalogExercise
from app.models.exercise import Exercise
from app.schemas.exercise import LEGACY_GROUPS, legacy_group

pytestmark = pytest.mark.anyio

VERSIONS = Path(__file__).parents[2] / "alembic" / "versions"
LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)


def migration(revision: str):
    path = next(VERSIONS.glob(f"{revision}_*.py"))
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def run(module, step: str) -> None:
    """Run a data migration's SQL against the test database."""
    statements: list[str] = []
    module.op = SimpleNamespace(execute=statements.append)
    getattr(module, step)()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        for sql in statements:
            await conn.execute(text(sql))
    await engine.dispose()


async def rows(model, *where):
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.connect() as conn:
        result = (await conn.execute(select(model.name, model.muscle_group, model.updated_at).where(*where))).all()
    await engine.dispose()
    return {name: (group, updated > LONG_AGO) for name, group, updated in result}


async def insert(model, values: list[dict]) -> None:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.execute(model.__table__.insert(), [{"updated_at": LONG_AGO, **v} for v in values])
        await conn.execute(update(model).values(updated_at=LONG_AGO))
    await engine.dispose()


async def age(*models) -> None:
    """Every row last changed long ago."""
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    async with engine.begin() as conn:
        for model in models:
            await conn.execute(update(model).values(updated_at=LONG_AGO))
    await engine.dispose()


async def test_the_migration_files_arms_by_name(client, user):
    seed = migration("d4f8a2c6e1b7").SEED
    await insert(CatalogExercise, [{"name": n, "zh": zh, "aka": aka, "muscle_group": m} for n, zh, aka, m in seed])
    mine = {"Tricep Pushdown": "arms", "Hammer Curl": "arms", "三頭下壓": "arms", "Wrist Roller": "arms", "Squat": "legs"}
    await insert(
        Exercise,
        [{"id": uuid.uuid4(), "user_id": user["id"], "name": n, "muscle_group": m} for n, m in mine.items()],
    )

    split = migration("e1f3b5c7a9d2")
    await run(split, "upgrade")

    library = await rows(CatalogExercise)
    arms = [name for name, _, _, group in seed if group == "arms"]
    assert {name: library[name][0] for name in arms} == {
        "Bicep Curl": "biceps",
        "Dumbbell Curl": "biceps",
        "Hammer Curl": "biceps",
        "Preacher Curl": "biceps",
        "Cable Curl": "biceps",
        "Tricep Pushdown": "triceps",
        "Overhead Tricep Extension": "triceps",
        "Cable Overhead Tricep Extension": "triceps",
        "Skull Crusher": "triceps",
        "Close-Grip Bench Press": "triceps",
    }
    # Only those changed (and say so with a later updated_at, so devices refetch).
    for name, _, _, group in seed:
        assert library[name] == ((library[name][0], True) if group == "arms" else (group, False)), name

    assert await rows(Exercise) == {
        "Tricep Pushdown": ("triceps", True),
        "Hammer Curl": ("biceps", True),
        "三頭下壓": ("triceps", True),
        "Wrist Roller": ("other", True),  # neither: forearms
        "Squat": ("legs", False),
    }

    await run(split, "downgrade")
    assert {name: library_group for name, (library_group, _) in (await rows(CatalogExercise)).items() if name in arms} == {
        name: "arms" for name in arms
    }


async def test_the_api_files_an_older_apps_arms_the_same_way(client, user):
    h = user["headers"]

    async def save(name: str, group: str | None):
        return await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": name, "muscle_group": group}, headers=h)

    assert (await save("Tricep Pushdown", "arms")).json()["muscle_group"] == "triceps"
    assert (await save("Hammer Curl", "arms")).json()["muscle_group"] == "biceps"
    assert (await save("Wrist Roller", "arms")).json()["muscle_group"] == "other"
    assert (await save("Cable Kickback", "triceps")).json()["muscle_group"] == "triceps"
    assert (await save("Forearm Curl", "forearms")).status_code == 422

    backup = {"exercises": [{"id": str(uuid.uuid4()), "name": "Skull Crusher", "muscle_group": "arms"}]}
    assert (await client.post("/api/v1/import", json=backup, headers=h)).status_code == 200
    groups = {e["name"]: e["muscle_group"] for e in (await client.get("/api/v1/exercises/", headers=h)).json()}
    assert groups["Skull Crusher"] == "triceps"


async def test_rows_an_older_server_wrote_still_read_back(client, user):
    """Written as "arms" between the migration and the new server going live."""
    await insert(Exercise, [{"id": uuid.uuid4(), "user_id": user["id"], "name": "Preacher Curl", "muscle_group": "arms"}])
    await insert(CatalogExercise, [{"name": "Dips", "zh": "雙槓撐體", "aka": None, "muscle_group": "arms"}])

    r = await client.get("/api/v1/exercises/", headers=user["headers"])
    assert r.status_code == 200, r.text
    assert {e["name"]: e["muscle_group"] for e in r.json()} == {"Preacher Curl": "biceps"}
    r = await client.get("/api/v1/catalog", headers=user["headers"])
    assert r.status_code == 200, r.text
    assert {e["name"]: e["muscle_group"] for e in r.json()} == {"Dips": "triceps"}


async def test_the_migration_files_back_legs_and_shoulders_by_name(client, user):
    seed = migration("d4f8a2c6e1b7").SEED
    await insert(CatalogExercise, [{"name": n, "zh": zh, "aka": aka, "muscle_group": m} for n, zh, aka, m in seed])
    mine = {
        "Lat Pulldown": "back",
        "Face Pull": "back",
        "Pendlay Row": "back",
        "Nordic Curl": "legs",
        "臀推": "legs",
        "Sled Push": "legs",
        "側平舉": "shoulders",
        "Landmine Press": "shoulders",
        "Bench Press": "chest",
    }
    await insert(
        Exercise,
        [{"id": uuid.uuid4(), "user_id": user["id"], "name": n, "muscle_group": m} for n, m in mine.items()],
    )
    await run(migration("e1f3b5c7a9d2"), "upgrade")
    await age(CatalogExercise, Exercise)  # so only the next step's changes show
    split = migration("b8c4e7f1a2d6")
    await run(split, "upgrade")

    library = await rows(CatalogExercise)
    moved = {"back", "legs", "shoulders"}
    assert {name: library[name][0] for name, _, _, group in seed if group in moved} == {
        "Deadlift": "lower_back",
        "Back Extension": "lower_back",
        "Pull-up": "lats",
        "Chin-up": "lats",
        "Lat Pulldown": "lats",
        "Straight-Arm Pulldown": "lats",
        "Barbell Row": "upper_back",
        "Dumbbell Row": "upper_back",
        "Seated Cable Row": "upper_back",
        "T-Bar Row": "upper_back",
        "Machine Row": "upper_back",
        "Shrug": "upper_back",
        "Face Pull": "rear_delts",
        "Rear Delt Fly": "rear_delts",
        "Chest-Supported Rear Delt Fly (45°)": "rear_delts",
        "Chest-Supported Rear Delt Fly (60°)": "rear_delts",
        "Chest-Supported Rear Delt Fly (75°)": "rear_delts",
        "Overhead Press": "front_delts",
        "Dumbbell Shoulder Press": "front_delts",
        "Machine Shoulder Press": "front_delts",
        "Arnold Press": "front_delts",
        "Front Raise": "front_delts",
        "Lateral Raise": "side_delts",
        "Cable Lateral Raise": "side_delts",
        "Upright Row": "side_delts",
        "Squat": "quads",
        "Front Squat": "quads",
        "Hack Squat": "quads",
        "Goblet Squat": "quads",
        "Leg Press": "quads",
        "Bulgarian Split Squat": "quads",
        "Lunge": "quads",
        "Leg Extension": "quads",
        "Romanian Deadlift": "hamstrings",
        "Leg Curl": "hamstrings",
        "Sumo Deadlift": "glutes",
        "Hip Thrust": "glutes",
        "Hip Abduction": "glutes",
        "Hip Adduction": "glutes",
        "Calf Raise": "calves",
        "Seated Calf Raise": "calves",
    }
    for name, zh, aka, group in seed:
        if group in moved:
            # The API would file it the same way, and the move shows in updated_at (devices refetch).
            assert library[name] == (legacy_group(group, name, zh, aka), True), name
        else:
            assert library[name][1] is False, name  # untouched

    assert await rows(Exercise) == {
        "Lat Pulldown": ("lats", True),
        "Face Pull": ("rear_delts", True),
        "Pendlay Row": ("upper_back", True),
        "Nordic Curl": ("hamstrings", True),
        "臀推": ("glutes", True),
        "Sled Push": ("quads", True),
        "側平舉": ("side_delts", True),
        "Landmine Press": ("front_delts", True),
        "Bench Press": ("chest", False),
    }

    await run(split, "downgrade")
    back = {name: group for name, (group, _) in (await rows(Exercise)).items()}
    assert back["Nordic Curl"] == "legs" and back["Lat Pulldown"] == "back" and back["側平舉"] == "shoulders"
    assert back["Face Pull"] == "shoulders"  # rear delts are shoulders now, wherever they came from


async def test_the_api_files_an_older_apps_back_legs_and_shoulders_the_same_way(client, user):
    h = user["headers"]

    async def save(name: str, group: str | None):
        return await client.put(f"/api/v1/exercises/{uuid.uuid4()}", json={"name": name, "muscle_group": group}, headers=h)

    assert (await save("Leg Curl", "legs")).json()["muscle_group"] == "hamstrings"
    assert (await save("Seated Calf Raise", "legs")).json()["muscle_group"] == "calves"
    assert (await save("Pull-up", "back")).json()["muscle_group"] == "lats"
    assert (await save("Reverse Pec Deck", "shoulders")).json()["muscle_group"] == "rear_delts"
    assert (await save("Hip Thrust", "glutes")).json()["muscle_group"] == "glutes"  # the new names as they are
    for old in LEGACY_GROUPS:
        r = await save(f"Mystery {old} move", old)  # never refused: there's always a fallback
        assert r.status_code < 300 and r.json()["muscle_group"] not in LEGACY_GROUPS, old

    backup = {"exercises": [{"id": str(uuid.uuid4()), "name": "Romanian Deadlift", "muscle_group": "legs"}]}
    assert (await client.post("/api/v1/import", json=backup, headers=h)).status_code == 200
    groups = {e["name"]: e["muscle_group"] for e in (await client.get("/api/v1/exercises/", headers=h)).json()}
    assert groups["Romanian Deadlift"] == "hamstrings"


async def test_old_groups_an_older_server_wrote_still_read_back_as_muscles(client, user):
    await insert(Exercise, [{"id": uuid.uuid4(), "user_id": user["id"], "name": "Lateral Raise", "muscle_group": "shoulders"}])
    await insert(CatalogExercise, [{"name": "Leg Curl", "zh": "腿彎舉", "aka": None, "muscle_group": "legs"}])

    r = await client.get("/api/v1/exercises/", headers=user["headers"])
    assert {e["name"]: e["muscle_group"] for e in r.json()} == {"Lateral Raise": "side_delts"}
    r = await client.get("/api/v1/catalog", headers=user["headers"])
    assert {e["name"]: e["muscle_group"] for e in r.json()} == {"Leg Curl": "hamstrings"}
