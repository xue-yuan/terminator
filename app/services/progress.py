"""Levels, XP and achievements (GET /progress).

The whole history is replayed in order, workout by workout (and weigh-in by
weigh-in), so each tier is dated by the workout that reached it, and each
workout's XP is what it earned when it happened (its streak bonus, its records).
What it earned is then banked (app/models/progress.py) and never taken back:
an edit can raise a workout's XP but not lower it, a deleted workout keeps its
XP, and an unlocked tier stays unlocked.

The rules are in app/services/achievements.py (written from ACHIEVEMENTS.md).
"""

from bisect import bisect_left
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_weight import BodyWeight
from app.models.catalog import CatalogExercise
from app.models.exercise import Exercise
from app.models.progress import AchievementUnlock, XpAward
from app.models.user import User
from app.models.workout import Workout, WorkoutItem, WorkoutSet
from app.schemas.exercise import LEGACY_GROUPS, legacy_group
from app.schemas.progress import AchievementOut, ProgressOut, TierOut, TitleOut
from app.services.achievements import (
    ACHIEVEMENTS,
    BY_ID,
    CATEGORIES,
    REGIONS,
    RULES,
    Achievement,
    find_tier,
    level_for,
    title_key,
    xp_for_level,
)
from app.services.errors import NotFound
from app.services.exercise import KG_PER_LB
from app.services.records import pr_set_ids

REGION_OF = {muscle: region for region, muscles in REGIONS.items() for muscle in muscles}
UPPER = ("chest", "arms")  # what "chicken legs" weighs against legs
CHUNK = 1000  # rows per INSERT (Postgres takes at most 32767 parameters)


@dataclass
class WorkoutFacts:
    """One workout, boiled down to what the rules look at."""

    id: UUID
    at: datetime  # local time
    duration_seconds: int | None
    working_sets: int = 0
    prs: int = 0
    volume_kg: float = 0.0
    exercises: set[UUID] = field(default_factory=set)
    muscle_sets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    region_sets: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    max_kg: dict[str, float] = field(default_factory=lambda: defaultdict(float))  # by lower-case exercise name
    max_reps: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    superset: bool = False


@dataclass
class Unlocked:
    at: datetime
    workout_id: UUID | None


def _week(day: date) -> date:
    return day - timedelta(days=day.weekday())


class Replay:
    """Walks the history in order, keeping every achievement's value up to date."""

    def __init__(self, body_weights: list[tuple[datetime, float]]):
        self.body_weights = sorted(body_weights)
        self.bw_times = [t for t, _ in self.body_weights]
        self.values: dict[str, float] = defaultdict(float)
        self.unlocked: dict[tuple[str, float], Unlocked] = {}
        self.workout_xp: dict[UUID, int] = {}
        self.state: dict[str, dict] = defaultdict(dict)  # per achievement, for those that need more than a number
        # Shared by several rules.
        self.workouts = 0
        self.week_counts: dict[date, int] = defaultdict(int)
        self.last_week: date | None = None
        self.streak = 0
        self.best_streak = 0
        self.last_day: date | None = None
        self.days: set[date] = set()
        self.weekends = 0
        self.week_regions: dict[date, set[str]] = defaultdict(set)
        self.full_body_weeks = 0
        self.prs = 0
        self.working_sets = 0
        self.volume_kg = 0.0
        self.exercises: set[UUID] = set()
        self.weigh_ins = 0

    # ---- body weight ----

    def body_weight_near(self, at: datetime, within_days: int) -> float | None:
        """The weigh-in closest in time to `at`, if one is within `within_days`."""
        i = bisect_left(self.bw_times, at)
        near = [self.body_weights[j] for j in (i - 1, i) if 0 <= j < len(self.body_weights)]
        near = [(abs(t - at), kg) for t, kg in near if abs(t - at) <= timedelta(days=within_days)]
        return min(near)[1] if near else None

    def add_weigh_in(self, at: datetime) -> None:
        self.weigh_ins += 1
        for a in ACHIEVEMENTS:
            if a.metric == "body_weight_entries":
                self.values[a.id] = self.weigh_ins
        self._check(at, None)

    # ---- workouts ----

    def add_workout(self, w: WorkoutFacts) -> None:
        day = w.at.date()
        week = _week(day)
        gap = (day - self.last_day).days if self.last_day else None
        first_this_week = self.week_counts[week] == 0

        self.workouts += 1
        self.week_counts[week] += 1
        if first_this_week:
            self.streak = self.streak + 1 if self.last_week == week - timedelta(weeks=1) else 1
            self.last_week = week
            self.best_streak = max(self.best_streak, self.streak)
        if day not in self.days:
            self.days.add(day)
            saturday = day - timedelta(days=1) if day.weekday() == 6 else day
            if saturday.weekday() == 5 and {saturday, saturday + timedelta(days=1)} <= self.days:
                self.weekends += 1
        self.last_day = max(self.last_day or day, day)
        was_full = len(self.week_regions[week]) == len(REGIONS)
        self.week_regions[week] |= {r for r, n in w.region_sets.items() if n and r in REGIONS}
        if not was_full and len(self.week_regions[week]) == len(REGIONS):
            self.full_body_weeks += 1
        self.prs += w.prs
        self.working_sets += w.working_sets
        self.volume_kg += w.volume_kg
        self.exercises |= w.exercises

        bonus = 0
        if first_this_week and self.streak >= 2:
            bonus = min(RULES["streak_bonus_per_week"] * self.streak, RULES["streak_bonus_max"])
        self.workout_xp[w.id] = (
            RULES["workout"]
            + RULES["working_set"] * min(w.working_sets, RULES["max_sets_per_workout"])
            + RULES["pr"] * w.prs
            + bonus
        )

        for a in ACHIEVEMENTS:
            self._update(a, w, gap)
        self._check(w.at, w.id)

    def _update(self, a: Achievement, w: WorkoutFacts, gap: int | None) -> None:
        p, v = a.params, self.values
        day = w.at.date()
        match a.metric:
            case "workouts":
                v[a.id] = self.workouts
            case "best_week_streak":
                v[a.id] = self.best_streak
            case "max_workouts_in_week":
                v[a.id] = max(v[a.id], self.week_counts[_week(day)])
            case "comebacks":
                # gap counts both workout days: the 1st to the 16th is 14 days off.
                v[a.id] += gap is not None and gap - 1 > p["rest_days"]
            case "prs":
                v[a.id] = self.prs
            case "bodyweight_ratio":
                kg = max(w.max_kg.get(name.lower(), 0) for name in p["exercises"])
                bw = self.body_weight_near(w.at, p["body_weight_within_days"]) if kg else None
                if bw:
                    v[a.id] = max(v[a.id], kg / bw)
            case "max_reps":
                v[a.id] = max(v[a.id], *(w.max_reps.get(name.lower(), 0) for name in p["exercises"]))
            case "total_volume_kg":
                v[a.id] = self.volume_kg
            case "max_workout_volume_kg":
                v[a.id] = max(v[a.id], w.volume_kg)
            case "working_sets":
                v[a.id] = self.working_sets
            case "distinct_exercises":
                v[a.id] = len(self.exercises)
            case "full_body_weeks":
                v[a.id] = self.full_body_weeks
            case "superset_workouts":
                v[a.id] += w.superset
            case "workouts_started_before":
                v[a.id] += w.at.hour < p["hour"]
            case "workouts_started_after":
                v[a.id] += w.at.hour >= p["hour"]
            case "workouts_longer_than":
                v[a.id] += (w.duration_seconds or 0) > p["minutes"] * 60
            case "weekends_both_days":
                v[a.id] = self.weekends
            case "workouts_on_date":
                v[a.id] += (day.month, day.day) == (p["month"], p["day"])
            case "muscle_sets":
                v[a.id] += w.muscle_sets.get(p["muscle"], 0)
            case "region_week_streak":
                s = self.state[a.id]
                sets = s.setdefault("sets", defaultdict(int))
                week = _week(day)
                before = sets[week]
                sets[week] += w.region_sets.get(p["region"], 0)
                if before < p["min_sets"] <= sets[week]:
                    s["streak"] = s.get("streak", 0) + 1 if s.get("last") == week - timedelta(weeks=1) else 1
                    s["last"] = week
                    v[a.id] = max(v[a.id], s["streak"])
            case "region_weekdays":
                if day.weekday() == p["weekday"]:
                    sets = self.state[a.id].setdefault("sets", defaultdict(int))
                    before = sets[day]
                    sets[day] += w.region_sets.get(p["region"], 0)
                    v[a.id] += before < p["min_sets"] <= sets[day]
            case "max_workout_region_sets":
                v[a.id] = max(v[a.id], w.region_sets.get(p["region"], 0))
            case "chicken_legs":
                window: deque = self.state[a.id].setdefault("window", deque())
                window.append((w.at, sum(w.region_sets.get(r, 0) for r in UPPER), w.region_sets.get("legs", 0)))
                while window[0][0] < w.at - timedelta(days=p["days"]):
                    window.popleft()
                upper = sum(u for _, u, _ in window)
                legs = sum(lg for _, _, lg in window)
                if upper >= p["min_sets"] and upper >= p["ratio"] * legs:
                    v[a.id] = 1
            case "level" | "body_weight_entries":
                pass  # levels come from the XP total; weigh-ins from add_weigh_in
            case _:
                raise ValueError(f"unknown metric {a.metric}")

    def _check(self, at: datetime, workout_id: UUID | None) -> None:
        for a in ACHIEVEMENTS:
            for t in a.tiers:
                key = (a.id, t.target)
                if key not in self.unlocked and a.metric != "level" and self.values[a.id] >= t.target:
                    self.unlocked[key] = Unlocked(at, workout_id)


class ProgressService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _muscles(self, user_id: int) -> dict[UUID, tuple[str, str]]:
        """Each of the user's exercises: (lower-case name, muscle group), the library's when it has none."""
        library = {
            name.lower(): legacy_group(group, name, zh, aka) if group in LEGACY_GROUPS else group
            for name, zh, aka, group in (
                await self.db.execute(
                    select(CatalogExercise.name, CatalogExercise.zh, CatalogExercise.aka, CatalogExercise.muscle_group)
                )
            ).all()
        }
        out = {}
        for id_, name, group in (
            await self.db.execute(select(Exercise.id, Exercise.name, Exercise.muscle_group).where(Exercise.user_id == user_id))
        ).all():
            if group in LEGACY_GROUPS:
                group = legacy_group(group, name)
            out[id_] = (name.lower(), group or library.get(name.lower()) or "other")
        return out

    async def _history(self, user_id: int, tz: ZoneInfo) -> list[WorkoutFacts]:
        muscles = await self._muscles(user_id)
        records = await pr_set_ids(self.db, user_id)
        rows = await self.db.execute(
            select(
                Workout.uuid,
                Workout.performed_at,
                Workout.duration_seconds,
                WorkoutItem.id,
                WorkoutItem.exercise_id,
                WorkoutItem.weight_unit,
                WorkoutItem.superset,
                WorkoutSet.id,
                WorkoutSet.kind,
                WorkoutSet.weight,
                WorkoutSet.reps,
            )
            .select_from(Workout)
            .outerjoin(WorkoutItem, WorkoutItem.workout_id == Workout.id)
            .outerjoin(WorkoutSet, WorkoutSet.item_id == WorkoutItem.id)
            .where(Workout.user_id == user_id)
            .order_by(Workout.performed_at, Workout.id, WorkoutItem.order, WorkoutSet.order)
        )
        workouts: dict[UUID, WorkoutFacts] = {}
        supersets: dict[UUID, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        for wid, at, duration, item_id, exercise_id, unit, superset, set_id, kind, weight, reps in rows:
            w = workouts.get(wid)
            if w is None:
                w = workouts[wid] = WorkoutFacts(wid, at.astimezone(tz), duration)
            if item_id is None:
                continue
            name, muscle = muscles.get(exercise_id, ("", "other"))
            w.exercises.add(exercise_id)
            if superset is not None:
                supersets[wid][superset].add(item_id)
            if set_id is None or kind != "working" or reps <= 0:
                continue
            kg = weight * KG_PER_LB if unit == "lb" else weight
            w.working_sets += 1
            w.prs += set_id in records
            w.volume_kg += kg * reps
            w.muscle_sets[muscle] += 1
            w.region_sets[REGION_OF.get(muscle, "other")] += 1
            w.max_kg[name] = max(w.max_kg[name], kg)
            w.max_reps[name] = max(w.max_reps[name], reps)
        for wid, groups in supersets.items():
            workouts[wid].superset = any(len(items) > 1 for items in groups.values())
        return list(workouts.values())

    async def _replay(self, user: User, tz: ZoneInfo) -> Replay:
        weigh_ins = (
            await self.db.execute(
                select(BodyWeight.measured_at, BodyWeight.weight, BodyWeight.unit).where(BodyWeight.user_id == user.id)
            )
        ).all()
        replay = Replay([(at, w * KG_PER_LB if unit == "lb" else w) for at, w, unit in weigh_ins])
        events: list[tuple[datetime, int, object]] = [(w.at, 1, w) for w in await self._history(user.id, tz)]
        events += [(at, 0, None) for at, _, _ in weigh_ins]
        for at, kind, w in sorted(events, key=lambda e: (e[0], e[1])):
            if kind:
                replay.add_workout(w)
            else:
                replay.add_weigh_in(at)
        return replay

    async def _bank(self, user_id: int, replay: Replay) -> None:
        """Keep what the history earns now, never lowering what was earned before."""
        awards = [{"user_id": user_id, "workout_id": wid, "xp": xp} for wid, xp in replay.workout_xp.items()]
        for i in range(0, len(awards), CHUNK):
            stmt = insert(XpAward).values(awards[i : i + CHUNK])
            await self.db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["user_id", "workout_id"],
                    set_={"xp": stmt.excluded.xp, "updated_at": func.now()},
                    where=XpAward.xp < stmt.excluded.xp,
                )
            )
        unlocks = [
            {"user_id": user_id, "achievement": a, "target": t, "unlocked_at": u.at, "workout_id": u.workout_id}
            for (a, t), u in replay.unlocked.items()
        ]
        await self._unlock(unlocks)

    async def _unlock(self, rows: list[dict]) -> None:
        for i in range(0, len(rows), CHUNK):
            await self.db.execute(insert(AchievementUnlock).values(rows[i : i + CHUNK]).on_conflict_do_nothing())

    async def _stored(self, user_id: int) -> dict[tuple[str, float], AchievementUnlock]:
        rows = (await self.db.execute(select(AchievementUnlock).where(AchievementUnlock.user_id == user_id))).scalars()
        return {(u.achievement, u.target): u for u in rows}

    async def progress(self, user: User, tz: ZoneInfo) -> ProgressOut:
        replay = await self._replay(user, tz)
        await self._bank(user.id, replay)

        stored = await self._stored(user.id)
        workout_xp = await self.db.scalar(
            select(func.coalesce(func.sum(XpAward.xp), 0)).where(XpAward.user_id == user.id)
        )
        tier_xp = sum(t.xp for a in ACHIEVEMENTS for t in a.tiers if (a.id, t.target) in stored)
        xp = int(workout_xp) + tier_xp
        level = level_for(xp)
        now = datetime.now(UTC)
        levels = BY_ID["level"]
        new = [
            {"user_id": user.id, "achievement": levels.id, "target": t.target, "unlocked_at": now, "workout_id": None}
            for t in levels.tiers
            if level >= t.target and (levels.id, t.target) not in stored
        ]
        if new:
            await self._unlock(new)
            stored = await self._stored(user.id)
        await self.db.commit()

        achievements = []
        for a in ACHIEVEMENTS:
            value = level if a.metric == "level" else replay.values[a.id]
            tiers = [
                TierOut(
                    target=t.target,
                    medal=t.medal,
                    xp=t.xp,
                    title=t.title,
                    description=t.description,
                    unlocked_at=stored[(a.id, t.target)].unlocked_at if (a.id, t.target) in stored else None,
                    workout_id=stored[(a.id, t.target)].workout_id if (a.id, t.target) in stored else None,
                )
                for t in a.tiers
            ]
            secret = a.hidden and not any(t.unlocked_at for t in tiers)
            if secret:  # a surprise: what it takes stays hidden until it's earned
                tiers = [t.model_copy(update={"title": None, "description": None}) for t in tiers]
            achievements.append(
                AchievementOut(
                    id=a.id,
                    category=a.category,
                    name=None if secret else a.name,
                    icon=a.icon,
                    metric=a.metric,
                    hidden=a.hidden,
                    value=0 if secret else round(value, 2),
                    tiers=tiers,
                )
            )
        return ProgressOut(
            xp=xp,
            level=level,
            level_xp=xp_for_level(level),
            next_level_xp=xp_for_level(level + 1),
            title=self._title(user, stored),
            rules=RULES,
            categories=[{"id": c, "name": n} for c, n in CATEGORIES],
            achievements=achievements,
        )

    @staticmethod
    def _title(user: User, stored) -> TitleOut | None:
        found = find_tier(user.title) if user.title else None
        if not found or (found[0].id, found[1].target) not in stored:
            return None
        return TitleOut(key=title_key(*found), title=found[1].title, medal=found[1].medal)

    async def set_title(self, user: User, key: str | None) -> TitleOut | None:
        """Wear an unlocked tier's title (None: none)."""
        if key is None:
            user.title = None
            await self.db.commit()
            return None
        found = find_tier(key)
        stored = await self._stored(user.id)
        if not found or (found[0].id, found[1].target) not in stored:
            raise NotFound("No such title unlocked")
        user.title = title_key(*found)
        await self.db.commit()
        return TitleOut(key=user.title, title=found[1].title, medal=found[1].medal)
