"""Who else trains here (GET /community): names, levels and worn titles, by name."""

import uuid

import pytest

from app.core.config import settings

pytestmark = pytest.mark.anyio

URL = "/api/v1/community"


async def train(client, h, day: int) -> None:
    body = {
        "performed_at": f"2026-11-{day:02d}T08:00:00Z",
        "items": [{"exercise_name": "Squat", "sets": [{"weight": 100, "reps": 5}] * 3}],
    }
    r = await client.put(f"/api/v1/workouts/{uuid.uuid4()}", json=body, headers=h)
    assert r.status_code == 201, r.text


async def test_everyone_by_name_with_level_and_title(client, make_user):
    sarah = await make_user()
    kyle = await make_user(email="kyle@example.com", name="Kyle Reese")
    await make_user(email="john@example.com", name="john Connor")
    for day in (2, 4, 6, 9):
        await train(client, kyle["headers"], day)
    await client.get("/api/v1/progress", headers=kyle["headers"])  # banks the XP
    r = await client.put("/api/v1/progress/title", json={"title": "workouts:1"}, headers=kyle["headers"])
    assert r.status_code == 200, r.text

    r = await client.get(URL, headers=sarah["headers"])
    assert r.status_code == 200, r.text
    players = r.json()
    assert [p["name"] for p in players] == ["john Connor", "Kyle Reese", "Sarah Connor"]  # by name, not by level
    assert [p["you"] for p in players] == [False, False, True]
    k = players[1]
    assert k["level"] > 1 and k["title"]["key"] == "workouts:1" and k["title"]["title"]
    assert players[0]["level"] == 1 and players[0]["title"] is None
    assert not any("email" in p or "xp" in p for p in players)


async def test_only_people_who_may_use_the_app(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@example.com")
    boss = await make_user(email="boss@example.com", name="Boss")
    await client.post("/api/v1/admin/access", json={"email": "sarah@example.com"}, headers=boss["headers"])
    sarah = await make_user()
    await make_user(email="removed@example.com", name="Removed Person")
    players = (await client.get(URL, headers=sarah["headers"])).json()
    assert [p["name"] for p in players] == ["Boss", "Sarah Connor"]
