"""The community's shared goals (一起達標) and the community titles they earn,
the feed (who finished a workout, and when) and high-fives (a gesture only)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.services.achievements import BY_ID

pytestmark = pytest.mark.anyio


async def train(client, h, at: str, items: list[dict] | None = None, duration: int | None = 3600) -> str:
    id_ = str(uuid.uuid4())
    body = {
        "performed_at": at,
        "duration_seconds": duration,
        "items": items or [{"exercise_name": "Squat", "sets": [{"weight": 100, "reps": 5}]}],
    }
    r = await client.put(f"/api/v1/workouts/{id_}", json=body, headers=h)
    assert r.status_code in (200, 201), r.text
    return id_


async def progress(client, h) -> dict:
    r = await client.get("/api/v1/progress", params={"tz": "Asia/Taipei"}, headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def community(p: dict, id_: str) -> dict:
    return next(a for a in p["achievements"] if a["id"] == id_)


def unlocked(p: dict, id_: str) -> list[float]:
    return [t["target"] for t in community(p, id_)["tiers"] if t["unlocked_at"]]


@pytest.fixture
async def pair(make_user):
    return await make_user(), await make_user(email="kyle@example.com", name="Kyle Reese")


async def test_weekly_goal_titles(client, pair):
    sarah, kyle = pair
    # Week of 2 Nov (goal 3, nothing before it): 4 workouts between them. Reached, both took part.
    for h, day in ((sarah, 2), (sarah, 4), (kyle, 3), (kyle, 5)):
        await train(client, h["headers"], f"2026-11-{day:02d}T10:00:00Z")
    # Week of 9 Nov (goal: 90% of 4): only 1. Missed.
    await train(client, sarah["headers"], "2026-11-10T10:00:00Z")
    # Week of 16 Nov (goal: 90% of the average of 4 and 1 = 2.25, so the minimum 3): 4. Reached, everyone came.
    for h, day in ((sarah, 16), (sarah, 18), (kyle, 17), (kyle, 19)):
        await train(client, h["headers"], f"2026-11-{day:02d}T10:00:00Z")

    p = await progress(client, sarah["headers"])
    assert community(p, "team_weeks")["value"] == 2
    assert unlocked(p, "team_weeks") == [1]
    assert community(p, "team_streak")["value"] == 1  # the missed week broke it
    # 16 Nov: everyone who trained in the 4 weeks before (Sarah and Kyle) trained again.
    assert unlocked(p, "full_house") == [1]
    tier = next(t for t in community(p, "full_house")["tiers"] if t["unlocked_at"])
    assert tier["unlocked_at"].startswith("2026-11-17")  # when the last of them came in

    # Community titles count towards XP like any other.
    tiers = sum(t["xp"] for a in p["achievements"] for t in a["tiers"] if t["unlocked_at"])
    assert BY_ID["team_weeks"].tiers[0].xp + BY_ID["full_house"].tiers[0].xp <= tiers
    assert p["xp"] >= tiers


async def test_running_totals_need_your_part(client, pair):
    sarah, kyle = pair
    bench = lambda n: {"exercise_name": "Bench Press", "sets": [{"weight": 60, "reps": 8}] * n}  # noqa: E731
    await train(client, sarah["headers"], "2026-11-02T10:00:00Z", [bench(100)] * 4 + [bench(80)])  # 480 sets
    await train(client, kyle["headers"], "2026-11-03T10:00:00Z", [bench(20)])  # 500 together; Kyle has 20 of 25

    s = await progress(client, sarah["headers"])
    k = await progress(client, kyle["headers"])
    assert (community(s, "team_bench")["value"], community(s, "team_bench")["own"]) == (500, 480)
    assert unlocked(s, "team_bench") == [500]
    assert (community(k, "team_bench")["own"], unlocked(k, "team_bench")) == (20, [])
    assert unlocked(k, "team_workouts") == []  # 2 workouts together, nowhere near 100

    await train(client, kyle["headers"], "2026-11-05T10:00:00Z", [bench(5)])
    k = await progress(client, kyle["headers"])
    assert unlocked(k, "team_bench") == [500]


async def test_community_titles_have_a_slot_of_their_own(client, pair):
    sarah, kyle = pair
    for h, day in ((sarah, 2), (sarah, 4), (kyle, 3)):
        await train(client, h["headers"], f"2026-11-{day:02d}T10:00:00Z")
    await progress(client, sarah["headers"])
    h = sarah["headers"]

    assert (await client.put("/api/v1/progress/title", json={"title": "team_weeks:1"}, headers=h)).status_code == 404
    r = await client.put("/api/v1/progress/community-title", json={"title": "workouts:1"}, headers=h)
    assert r.status_code == 404  # a regular title doesn't go there either
    r = await client.put("/api/v1/progress/community-title", json={"title": "team_weeks:1"}, headers=h)
    assert (r.status_code, r.json()["title"]) == (200, "Team Player")
    await client.put("/api/v1/progress/title", json={"title": "workouts:1"}, headers=h)

    p = await progress(client, h)
    assert (p["title"]["title"], p["community_title"]["title"]) == ("First Rep", "Team Player")
    me = next(x for x in (await client.get("/api/v1/community", headers=kyle["headers"])).json() if x["name"] == "Sarah Connor")
    assert (me["title"]["title"], me["community_title"]["title"]) == ("First Rep", "Team Player")
    r = await client.put("/api/v1/progress/community-title", json={"title": None}, headers=h)
    assert r.json() is None


async def test_this_weeks_goal(client, pair):
    sarah, kyle = pair
    now = datetime.now(UTC)
    await train(client, sarah["headers"], (now - timedelta(minutes=5)).isoformat())
    r = await client.get("/api/v1/community/goal", headers=kyle["headers"])
    assert r.status_code == 200, r.text
    goal = r.json()
    assert (goal["target"], goal["total"], goal["reached"], goal["trained"]) == (3, 1, False, [sarah["id"]])
    await train(client, kyle["headers"], (now - timedelta(minutes=3)).isoformat())
    await train(client, kyle["headers"], (now - timedelta(minutes=1)).isoformat())
    goal = (await client.get("/api/v1/community/goal", headers=kyle["headers"])).json()
    assert (goal["total"], goal["reached"], goal["weeks_reached"], goal["streak"]) == (3, True, 1, 1)


async def test_feed_says_who_and_when_and_takes_high_fives(client, pair):
    sarah, kyle = pair
    mine = await train(client, sarah["headers"], "2026-11-20T10:00:00Z", duration=1800)
    theirs = await train(client, kyle["headers"], "2026-11-20T09:00:00Z", duration=None)
    feed = (await client.get("/api/v1/community/feed", headers=kyle["headers"])).json()
    assert [(f["name"], f["at"], f["you"]) for f in feed] == [
        ("Sarah Connor", "2026-11-20T10:30:00Z", False),  # finished half an hour after it started
        ("Kyle Reese", "2026-11-20T09:00:00Z", True),
    ]
    assert set(feed[0]) == {"workout_id", "player_id", "name", "at", "you", "high_fived", "high_fivers"}

    url = f"/api/v1/community/feed/{mine}/high-five"
    assert (await client.put(url, headers=kyle["headers"])).status_code == 204
    assert (await client.put(url, headers=kyle["headers"])).status_code == 204  # once is enough
    own = f"/api/v1/community/feed/{theirs}/high-five"
    assert (await client.put(own, headers=kyle["headers"])).status_code == 400
    missing = f"/api/v1/community/feed/{uuid.uuid4()}/high-five"
    assert (await client.put(missing, headers=kyle["headers"])).status_code == 404

    kyle_view = (await client.get("/api/v1/community/feed", headers=kyle["headers"])).json()
    assert (kyle_view[0]["high_fived"], kyle_view[0]["high_fivers"]) == (True, [])
    sarah_view = (await client.get("/api/v1/community/feed", headers=sarah["headers"])).json()
    assert (sarah_view[0]["you"], sarah_view[0]["high_fivers"]) == (True, ["Kyle Reese"])
    inbox = (await client.get("/api/v1/community/high-fives", headers=sarah["headers"])).json()
    assert [(x["name"], x["workout_id"]) for x in inbox] == [("Kyle Reese", mine)]
    later = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    assert (await client.get("/api/v1/community/high-fives", params={"since": later}, headers=sarah["headers"])).json() == []

    # High-fives earn nothing.
    before = (await progress(client, sarah["headers"]))["xp"]
    assert (await client.delete(url, headers=kyle["headers"])).status_code == 204
    assert (await client.get("/api/v1/community/high-fives", headers=sarah["headers"])).json() == []
    assert (await progress(client, sarah["headers"]))["xp"] == before

    page = (await client.get("/api/v1/community/feed", params={"before": "2026-11-20T10:00:00Z"}, headers=sarah["headers"])).json()
    assert [f["name"] for f in page] == ["Kyle Reese"]


async def test_sync_state_follows_the_community(client, pair):
    sarah, kyle = pair
    state = lambda: client.get("/api/v1/sync/state", headers=sarah["headers"])  # noqa: E731
    first = (await state()).json()
    theirs = await train(client, kyle["headers"], "2026-11-20T09:00:00Z")
    second = (await state()).json()
    assert second["community"] != first["community"]
    assert second["progress"] != first["progress"]  # Kyle's workouts count towards Sarah's community titles
    await train(client, sarah["headers"], "2026-11-21T09:00:00Z")
    third = (await state()).json()
    await client.put(f"/api/v1/community/feed/{theirs}/high-five", headers=sarah["headers"])
    assert (await state()).json()["community"] != third["community"]
