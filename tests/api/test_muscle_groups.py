"""Arms split into biceps and triceps: the migration and the API sort an exercise the same way."""

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
