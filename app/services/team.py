"""The community's shared goals (一起達標), which earn community titles
(category "community" in app/services/achievements.py, written from the
「社群稱號」 part of ACHIEVEMENTS.md):

- Every week (Monday to Sunday in COMMUNITY_TZ) there's one goal for everyone
  together: so many workouts between them. It's 90% of the weekly average of the
  4 weeks before (rounded), at least 3. Training that week is taking part.
- Running totals of everyone together (bench sets, workouts, tonnage...): a tier
  is reached once the total is there and your own part is at least `share` of it.

Worked out from every member's workouts, so the dates are when it happened.
"""

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fractions import Fraction
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutItem, WorkoutSet
from app.services.access import members
from app.services.achievements import ACHIEVEMENTS, COMMUNITY
from app.services.exercise import _WEIGHT_KG

MIN_TARGET = 3
TARGET_SHARE = Fraction(9, 10)  # exact, so a half is a half (no 4.4999… from floats)
LOOKBACK_WEEKS = 4


def weekly_target(totals: list[int]) -> int:
    """The goal after weeks with these totals: 90% of their average, rounded half up
    (四捨五入: 4.5 is 5, where Python's round() would give 4), at least MIN_TARGET."""
    if not totals:
        return MIN_TARGET
    return max(MIN_TARGET, math.floor(TARGET_SHARE * sum(totals) / len(totals) + Fraction(1, 2)))


@dataclass
class Done:
    """One finished workout, as the goals count it."""

    user_id: int
    workout_id: UUID
    at: datetime
    sets: dict[str, int] = field(default_factory=lambda: defaultdict(int))  # working sets by lower-case exercise name
    volume_kg: float = 0.0
    distance_m: float = 0.0


@dataclass
class Week:
    start: date
    target: int
    total: int
    reached_at: datetime | None  # the workout that made the count
    first: dict[int, datetime]  # each member's first workout that week

    @property
    def reached(self) -> bool:
        return self.reached_at is not None


@dataclass
class Standing:
    """One member's community achievements: value (and own part) per achievement, and tiers reached."""

    values: dict[str, float] = field(default_factory=dict)
    own: dict[str, float] = field(default_factory=dict)
    unlocked: dict[tuple[str, float], datetime] = field(default_factory=dict)


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


class TeamService:
    def __init__(self, db: AsyncSession, tz: ZoneInfo | None = None):
        self.db = db
        self.tz = tz or ZoneInfo(settings.COMMUNITY_TZ)

    async def _done(self, user_ids: list[int]) -> list[Done]:
        """Every member's workouts, oldest first, with what the goals count."""
        if not user_ids:
            return []
        counted = (WorkoutSet.kind == "working") & (
            (WorkoutSet.reps > 0) | (WorkoutSet.duration_seconds > 0) | (WorkoutSet.distance_m > 0)
        )
        rows = await self.db.execute(
            select(
                Workout.user_id,
                Workout.uuid,
                Workout.performed_at,
                func.lower(Exercise.name),
                func.count(WorkoutSet.id).filter(counted),
                func.coalesce(func.sum(_WEIGHT_KG * WorkoutSet.reps).filter(counted), 0.0),
                func.coalesce(func.sum(WorkoutSet.distance_m).filter(counted), 0.0),
            )
            .select_from(Workout)
            .outerjoin(WorkoutItem, WorkoutItem.workout_id == Workout.id)
            .outerjoin(Exercise, Exercise.id == WorkoutItem.exercise_id)
            .outerjoin(WorkoutSet, WorkoutSet.item_id == WorkoutItem.id)
            .where(Workout.user_id.in_(user_ids))
            .group_by(Workout.id, Workout.user_id, Workout.uuid, Workout.performed_at, func.lower(Exercise.name))
            .order_by(Workout.performed_at, Workout.id)
        )
        done: dict[UUID, Done] = {}
        for user_id, uuid, at, name, sets, volume, distance in rows:
            d = done.get(uuid)
            if d is None:
                d = done[uuid] = Done(user_id, uuid, at)
            if name is not None:
                d.sets[name] += sets
                d.volume_kg += float(volume)
                d.distance_m += float(distance)
        return list(done.values())

    def _weeks(self, done: list[Done], today: date) -> list[Week]:
        """Every week from the first workout to this one, with its goal."""
        if not done:
            return [Week(_monday(today), MIN_TARGET, 0, None, {})]
        by_week: dict[date, list[Done]] = defaultdict(list)
        for d in done:
            by_week[_monday(d.at.astimezone(self.tz).date())].append(d)
        weeks: list[Week] = []
        week = min(by_week)
        last = max(_monday(today), max(by_week))
        while week <= last:
            these = sorted(by_week.get(week, []), key=lambda d: d.at)
            target = weekly_target([w.total for w in weeks[-LOOKBACK_WEEKS:]])
            first: dict[int, datetime] = {}
            for d in these:
                first.setdefault(d.user_id, d.at)
            reached = these[target - 1].at if len(these) >= target else None
            weeks.append(Week(week, target, len(these), reached, first))
            week += timedelta(weeks=1)
        return weeks

    async def _load(self, now: datetime | None = None):
        people = await members(self.db)
        done = await self._done([u.id for u in people])
        today = (now or datetime.now(self.tz)).astimezone(self.tz).date()
        return people, done, self._weeks(done, today)

    async def this_week(self, user_id: int, now: datetime | None = None) -> tuple[Week, list[Week]]:
        """This week's goal, and every week before it."""
        _, _, weeks = await self._load(now)
        return weeks[-1], weeks

    async def standing(self, user_id: int, now: datetime | None = None) -> Standing:
        """`user_id`'s community achievements, from everyone's history."""
        _, done, weeks = await self._load(now)
        out = Standing()
        for a in ACHIEVEMENTS:
            if a.category != COMMUNITY:
                continue
            match a.metric:
                case "team_weeks" | "team_streak" | "full_house_weeks":
                    self._weekly(a, weeks, user_id, out)
                case "team_sets" | "team_workouts" | "team_volume_kg" | "team_distance_m":
                    self._together(a, done, user_id, out)
                case _:
                    raise ValueError(f"unknown community metric {a.metric}")
        return out

    @staticmethod
    def _reach(a, out: Standing, value: float, at: datetime) -> None:
        out.values[a.id] = max(out.values.get(a.id, 0), value)
        for t in a.tiers:
            if value >= t.target:
                out.unlocked.setdefault((a.id, t.target), at)

    def _weekly(self, a, weeks: list[Week], user_id: int, out: Standing) -> None:
        out.values[a.id] = 0
        count = 0
        streak = 0
        for i, w in enumerate(weeks):
            mine = w.first.get(user_id)
            if a.metric == "full_house_weeks":
                recent = set().union(*(set(x.first) for x in weeks[max(0, i - LOOKBACK_WEEKS) : i]))
                everyone = recent | ({user_id} if mine else set())
                if mine and len(everyone) >= 2 and everyone <= set(w.first):
                    count += 1
                    self._reach(a, out, count, max(w.first[u] for u in everyone))
                continue
            if w.reached and mine:
                count += 1
                streak += 1
                at = max(w.reached_at, mine)
                self._reach(a, out, count if a.metric == "team_weeks" else streak, at)
            elif i < len(weeks) - 1:
                streak = 0  # a week that's over without it; the week under way can still make it

    def _together(self, a, done: list[Done], user_id: int, out: Standing) -> None:
        names = [n.lower() for n in a.params.get("exercises", [])]

        def amount(d: Done) -> float:
            match a.metric:
                case "team_sets":
                    return sum(d.sets.get(n, 0) for n in names)
                case "team_workouts":
                    return 1
                case "team_volume_kg":
                    return d.volume_kg
                case _:
                    return d.distance_m

        total = own = 0.0
        for d in done:
            x = amount(d)
            if not x:
                continue
            total += x
            if d.user_id == user_id:
                own += x
            for t in a.tiers:
                if total >= t.target and own >= math.ceil(t.target * a.params["share"]):
                    out.unlocked.setdefault((a.id, t.target), d.at)
        out.values[a.id] = total
        out.own[a.id] = own
