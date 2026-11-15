from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.summary import week_streak

TAIPEI = ZoneInfo("Asia/Taipei")
MON = date(2026, 11, 9)


@pytest.mark.parametrize(
    ("weeks_ago", "expected"),
    [
        ([], 0),
        ([0], 1),
        ([0, 1, 2], 3),
        ([1, 2], 2),  # nothing yet this week: streak still alive
        ([0, 2, 3], 1),
        ([2, 3], 0),  # missed all of last week
    ],
)
def test_week_streak(weeks_ago, expected):
    active = {MON - timedelta(weeks=n) for n in weeks_ago}
    assert week_streak(active, MON) == expected


@pytest.mark.anyio
async def test_summary_uses_callers_time_zone(client, user):
    # Monday 07:00 in Taipei is Sunday 23:00 UTC: it belongs to this week in Taipei
    # but to last week in UTC.
    now = datetime.now(TAIPEI)
    monday = (now - timedelta(days=now.weekday())).replace(hour=7, minute=0, second=0, microsecond=0)
    if monday + timedelta(hours=1) > now:
        pytest.skip("too early on Monday in Taipei for this scenario")
    w = {"performed_at": monday.isoformat(), "items": []}
    assert (await client.post("/api/v1/workouts/", json=w, headers=user["headers"])).status_code == 201

    tpe = (await client.get("/api/v1/users/me/summary?tz=Asia/Taipei", headers=user["headers"])).json()
    assert tpe["workouts_this_week"] == 1
    assert tpe["week_streak"] == 1
    assert tpe["total_workouts"] == 1

    utc = (await client.get("/api/v1/users/me/summary?tz=UTC", headers=user["headers"])).json()
    assert utc["workouts_this_week"] == 0
    assert utc["week_streak"] == 1  # last week counts while this week is in progress


@pytest.mark.anyio
async def test_summary_rejects_unknown_tz(client, user):
    r = await client.get("/api/v1/users/me/summary?tz=Mars/Base", headers=user["headers"])
    assert r.status_code == 422
