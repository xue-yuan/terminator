"""A week's or a month's training in review (GET /recap): totals against the
period before, the records broken, the exercises and muscles worked, the XP
banked and the titles reached."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.progress import AchievementUnlock, XpAward
from app.models.workout import Workout, WorkoutItem
from app.schemas.recap import Period, RecapExercise, RecapOut, RecapRecord, RecapTotals, RecapUnlock
from app.services.achievements import BY_ID
from app.services.exercise import KG_PER_LB
from app.services.progress import ProgressService
from app.services.records import mark_prs


def period_bounds(period: Period, day: date) -> tuple[date, date, date]:
    """(start, end, previous start) of the period `day` falls in; end is exclusive."""
    if period == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(weeks=1), start - timedelta(weeks=1)
    start = day.replace(day=1)
    end = (start + timedelta(days=32)).replace(day=1)
    previous = (start - timedelta(days=1)).replace(day=1)
    return start, end, previous


def _is_logged(s) -> bool:
    """A working set that counts: reps, or a time or a distance (timed and cardio sets)."""
    return s.kind == "working" and (s.reps > 0 or (s.duration_seconds or 0) > 0 or (s.distance_m or 0) > 0)


def _totals(workouts: list[Workout]) -> RecapTotals:
    t = RecapTotals(workouts=len(workouts))
    for w in workouts:
        t.duration_seconds += w.duration_seconds or 0
        for item in w.items:
            to_kg = KG_PER_LB if item.weight_unit == "lb" else 1.0
            for s in item.sets:
                if not _is_logged(s):
                    continue
                t.working_sets += 1
                t.reps += s.reps
                t.volume_kg += s.weight * to_kg * s.reps
                t.distance_m += s.distance_m or 0
                t.cardio_seconds += s.duration_seconds or 0
    t.volume_kg = round(t.volume_kg, 1)
    return t


class RecapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _workouts(self, user_id: int, start: datetime, end: datetime) -> list[Workout]:
        stmt = (
            select(Workout)
            .where(Workout.user_id == user_id, Workout.performed_at >= start, Workout.performed_at < end)
            .options(selectinload(Workout.items).selectinload(WorkoutItem.sets))
            .order_by(Workout.performed_at, Workout.id)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def recap(self, user_id: int, period: Period, day: date, tz: ZoneInfo) -> RecapOut:
        start, end, previous_start = period_bounds(period, day)

        def at(d: date) -> datetime:
            return datetime.combine(d, time.min, tzinfo=tz)

        workouts = await self._workouts(user_id, at(start), at(end))
        before = await self._workouts(user_id, at(previous_start), at(start))
        await mark_prs(self.db, user_id, workouts)
        muscles_of = await ProgressService(self.db).exercise_muscles(user_id)

        records: list[RecapRecord] = []
        exercises: dict = {}
        muscles: dict[str, int] = defaultdict(int)
        for w in workouts:
            for item in w.items:
                to_kg = KG_PER_LB if item.weight_unit == "lb" else 1.0
                for s in item.sets:
                    if not _is_logged(s):
                        continue
                    entry = exercises.setdefault(
                        item.exercise_id,
                        RecapExercise(exercise_id=item.exercise_id, exercise_name=item.exercise_name, sets=0, volume_kg=0),
                    )
                    entry.sets += 1
                    entry.volume_kg += s.weight * to_kg * s.reps
                    muscles[muscles_of.get(item.exercise_id, ("", "other"))[1]] += 1
                    if s.pr:
                        records.append(
                            RecapRecord(
                                exercise_id=item.exercise_id,
                                exercise_name=item.exercise_name,
                                kinds=s.pr,
                                weight=s.weight,
                                reps=s.reps,
                                weight_unit=item.weight_unit,
                                duration_seconds=s.duration_seconds,
                                distance_m=s.distance_m,
                                performed_at=w.performed_at,
                                workout_id=w.uuid,
                            )
                        )
        for entry in exercises.values():
            entry.volume_kg = round(entry.volume_kg, 1)

        xp = 0
        if workouts:
            xp = await self.db.scalar(
                select(func.coalesce(func.sum(XpAward.xp), 0)).where(
                    XpAward.user_id == user_id, XpAward.workout_id.in_([w.uuid for w in workouts])
                )
            )
        unlocks = []
        rows = await self.db.execute(
            select(AchievementUnlock)
            .where(
                AchievementUnlock.user_id == user_id,
                AchievementUnlock.unlocked_at >= at(start),
                AchievementUnlock.unlocked_at < at(end),
            )
            .order_by(AchievementUnlock.unlocked_at)
        )
        for u in rows.scalars():
            achievement = BY_ID.get(u.achievement)
            tier = next((t for t in achievement.tiers if t.target == u.target), None) if achievement else None
            if tier:
                unlocks.append(
                    RecapUnlock(
                        achievement=achievement.id,
                        icon=achievement.icon,
                        title=tier.title,
                        medal=tier.medal,
                        unlocked_at=u.unlocked_at,
                    )
                )

        return RecapOut(
            period=period,
            start=start,
            end=end,
            totals=_totals(workouts),
            previous=_totals(before),
            days=sorted({w.performed_at.astimezone(tz).date() for w in workouts}),
            records=records,
            exercises=sorted(exercises.values(), key=lambda e: (-e.sets, -e.volume_kg, e.exercise_name.lower())),
            muscles=dict(muscles),
            xp=int(xp or 0),
            unlocks=unlocks,
        )
