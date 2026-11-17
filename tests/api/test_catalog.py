import importlib.util
from pathlib import Path
from typing import get_args

import pytest

from app.core.config import settings
from app.schemas.catalog import CatalogIn
from app.schemas.exercise import MuscleGroup

pytestmark = pytest.mark.anyio

URL = "/api/v1/catalog"


@pytest.fixture
async def admin(make_user, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@example.com")
    return await make_user(email="boss@example.com", name="Boss")


@pytest.fixture
async def member(client, admin, make_user):
    """Someone the admin let in."""
    await client.post("/api/v1/admin/access", json={"email": "sarah@example.com"}, headers=admin["headers"])
    return await make_user(email="sarah@example.com")


async def test_admin_adds_edits_and_removes_exercises_everyone_sees(client, admin, member):
    sarah = member
    assert (await client.get(URL, headers=sarah["headers"])).json() == []

    r = await client.post(
        URL,
        json={"name": " Decline Chest Press Machine ", "zh": "下斜推胸機", "aka": "  機械下胸   下胸機械 ", "muscle_group": "chest"},
        headers=admin["headers"],
    )
    assert r.status_code == 201
    entry = r.json()
    assert entry | {"id": None} == {
        "id": None,
        "name": "Decline Chest Press Machine",
        "zh": "下斜推胸機",
        "aka": "機械下胸 下胸機械",
        "muscle_group": "chest",
    }
    await client.post(URL, json={"name": "Ab Wheel Rollout", "muscle_group": "core"}, headers=admin["headers"])

    r = await client.get(URL, headers=sarah["headers"])
    assert [e["name"] for e in r.json()] == ["Ab Wheel Rollout", "Decline Chest Press Machine"]  # by name

    r = await client.put(
        f"{URL}/{entry['id']}",
        json={"name": "Decline Press Machine", "zh": "", "aka": None, "muscle_group": "chest"},
        headers=admin["headers"],
    )
    assert r.status_code == 200
    assert (r.json()["name"], r.json()["zh"], r.json()["aka"]) == ("Decline Press Machine", None, None)

    assert (await client.delete(f"{URL}/{entry['id']}", headers=admin["headers"])).status_code == 204
    assert (await client.delete(f"{URL}/{entry['id']}", headers=admin["headers"])).status_code == 204  # idempotent
    assert [e["name"] for e in (await client.get(URL, headers=sarah["headers"])).json()] == ["Ab Wheel Rollout"]


async def test_names_are_unique_ignoring_case(client, admin):
    r = await client.post(URL, json={"name": "Pec Deck", "muscle_group": "chest"}, headers=admin["headers"])
    pec_deck = r.json()["id"]
    other = (await client.post(URL, json={"name": "Cable Fly", "muscle_group": "chest"}, headers=admin["headers"])).json()

    r = await client.post(URL, json={"name": "pec deck", "muscle_group": "chest"}, headers=admin["headers"])
    assert (r.status_code, r.json()["detail"]) == (409, '"Pec Deck" is already in the library')
    r = await client.put(f"{URL}/{other['id']}", json={"name": "PEC DECK", "muscle_group": "chest"}, headers=admin["headers"])
    assert r.status_code == 409
    # Changing only the case of its own name is fine.
    r = await client.put(f"{URL}/{pec_deck}", json={"name": "pec deck", "muscle_group": "chest"}, headers=admin["headers"])
    assert (r.status_code, r.json()["name"]) == (200, "pec deck")


async def test_bad_entries_are_refused(client, admin):
    for body in (
        {"name": "", "muscle_group": "chest"},
        {"name": "Squat"},  # muscle group is required
        {"name": "Squat", "muscle_group": "glutes"},
        {"name": "Squat", "muscle_group": "legs", "zh": "x" * 101},
    ):
        assert (await client.post(URL, json=body, headers=admin["headers"])).status_code == 422, body
    r = await client.put(f"{URL}/999", json={"name": "Squat", "muscle_group": "legs"}, headers=admin["headers"])
    assert r.status_code == 404


async def test_only_admins_change_the_library(client, admin, member):
    user = member
    entry = (await client.post(URL, json={"name": "Squat", "muscle_group": "legs"}, headers=admin["headers"])).json()
    body = {"name": "Back Squat", "muscle_group": "legs"}
    assert (await client.post(URL, json=body, headers=user["headers"])).status_code == 403
    assert (await client.put(f"{URL}/{entry['id']}", json=body, headers=user["headers"])).status_code == 403
    assert (await client.delete(f"{URL}/{entry['id']}", headers=user["headers"])).status_code == 403
    assert (await client.get(URL)).status_code == 401


async def test_every_change_moves_the_sync_fingerprint(client, admin):
    async def fingerprint():
        return (await client.get("/api/v1/sync/state", headers=admin["headers"])).json()["catalog"]

    first = (await client.post(URL, json={"name": "Deadlift", "muscle_group": "back"}, headers=admin["headers"])).json()
    seen = [await fingerprint()]
    entry = (await client.post(URL, json={"name": "Squat", "muscle_group": "legs"}, headers=admin["headers"])).json()
    seen.append(await fingerprint())
    await client.put(f"{URL}/{entry['id']}", json={"name": "Squat", "zh": "深蹲", "muscle_group": "legs"}, headers=admin["headers"])
    seen.append(await fingerprint())
    await client.delete(f"{URL}/{first['id']}", headers=admin["headers"])
    seen.append(await fingerprint())
    assert len(set(seen)) == 4


def test_the_migrated_catalog_is_valid():
    """The library every deploy starts with (moved from the frontend)."""
    path = next(Path(__file__).parents[2].glob("alembic/versions/*_exercise_library.py"))
    spec = importlib.util.spec_from_file_location("exercise_library", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    names = [name.lower() for name, *_ in migration.SEED]
    assert len(names) == len(set(names)) > 50
    for name, zh, aka, muscle in migration.SEED:
        entry = CatalogIn(name=name, zh=zh, aka=aka, muscle_group=muscle)
        assert (entry.name, entry.zh, entry.aka) == (name, zh, aka), name  # stored as written
        # "arms" was split into biceps and triceps later (e1f3b5c7a9d2, tested in test_muscle_groups.py).
        assert entry.muscle_group in (("biceps", "triceps") if muscle == "arms" else (muscle,)), name
        assert zh and entry.muscle_group in get_args(MuscleGroup), name
