from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutItem, WorkoutSet, utcnow
from app.schemas.workout import WorkoutIn
from app.services.errors import Invalid, NotFound
from app.services.exercise import ExerciseService
from app.services.plan import PlanService
from app.services.records import mark_prs

_LOAD_ITEMS = selectinload(Workout.items).selectinload(WorkoutItem.sets)


def _build_items(data: WorkoutIn, exercises: list[Exercise]) -> list[WorkoutItem]:
    return [
        WorkoutItem(
            exercise=exercises[i],
            weight_unit=item.weight_unit,
            superset=item.superset,
            order=i,
            sets=[
                WorkoutSet(reps=s.reps, weight=s.weight, rpe=s.rpe, kind=s.kind, order=j)
                for j, s in enumerate(item.sets)
            ],
        )
        for i, item in enumerate(data.items)
    ]


class WorkoutService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(self, user_id: int, *, skip: int = 0, limit: int | None = 50) -> Sequence[Workout]:
        """Most recent first (all of them with `limit=None`)."""
        stmt = (
            select(Workout)
            .where(Workout.user_id == user_id)
            .options(_LOAD_ITEMS)
            .order_by(Workout.performed_at.desc(), Workout.id.desc())
            .offset(skip)
            .limit(limit)
        )
        workouts = (await self.db.execute(stmt)).scalars().all()
        await mark_prs(self.db, user_id, workouts)
        return workouts

    async def _find(self, workout_uuid: UUID) -> Workout | None:
        stmt = (
            select(Workout)
            .where(Workout.uuid == workout_uuid)
            .options(_LOAD_ITEMS)
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get(self, user_id: int, workout_uuid: UUID) -> Workout:
        workout = await self._find(workout_uuid)
        if workout is None or workout.user_id != user_id:
            raise NotFound
        await mark_prs(self.db, user_id, [workout])
        return workout

    async def _check_plan_day(self, user_id: int, plan_day_id: int | None) -> None:
        if plan_day_id is not None and not await PlanService(self.db).is_day_visible(
            user_id, plan_day_id
        ):
            raise Invalid("plan_day_id does not refer to one of your plans")

    async def upsert(self, user_id: int, workout_uuid: UUID, data: WorkoutIn) -> tuple[Workout, bool]:
        """Create or fully replace a workout. Returns (workout, created)."""
        await self._check_plan_day(user_id, data.plan_day_id)
        for attempt in range(2):
            existing = await self._find(workout_uuid)
            if existing is not None and existing.user_id != user_id:
                raise NotFound
            exercises = await ExerciseService(self.db).resolve(
                user_id, [(item.exercise_id, item.exercise_name) for item in data.items]
            )
            fields = data.model_dump(exclude={"items", "id"})
            if existing is None:
                self.db.add(
                    Workout(uuid=workout_uuid, user_id=user_id, items=_build_items(data, exercises), **fields)
                )
            else:
                for key, value in fields.items():
                    setattr(existing, key, value)
                existing.items = _build_items(data, exercises)
                existing.updated_at = utcnow()
            try:
                await self.db.commit()
            except IntegrityError:
                # A concurrent request created the same workout or exercise first:
                # retry, which now finds it.
                await self.db.rollback()
                if attempt:
                    raise
                continue
            return await self.get(user_id, workout_uuid), existing is None
        raise AssertionError("unreachable")

    async def import_many(self, user_id: int, workouts: Sequence[tuple[UUID, WorkoutIn]]) -> tuple[int, int]:
        """Create or replace many workouts in one transaction (all or nothing).
        References to plan days the user can't see are dropped (ids don't carry
        over between accounts). Returns (created, updated)."""
        if not workouts:
            return 0, 0
        ids = [workout_id for workout_id, _ in workouts]
        found = (
            await self.db.execute(select(Workout).where(Workout.uuid.in_(ids)).options(_LOAD_ITEMS))
        ).scalars().all()
        existing = {w.uuid: w for w in found}
        if any(w.user_id != user_id for w in found):
            raise Invalid("Some workouts belong to another account")

        refs = [(item.exercise_id, item.exercise_name) for _, data in workouts for item in data.items]
        exercises = iter(await ExerciseService(self.db).resolve(user_id, refs))
        plan_service = PlanService(self.db)
        visible_days = {
            day_id
            for day_id in {data.plan_day_id for _, data in workouts if data.plan_day_id is not None}
            if await plan_service.is_day_visible(user_id, day_id)
        }

        created = 0
        for workout_id, data in workouts:
            items = _build_items(data, [next(exercises) for _ in data.items])
            fields = data.model_dump(exclude={"items", "id", "import_key"})
            if fields["plan_day_id"] not in visible_days:
                fields["plan_day_id"] = None
            workout = existing.get(workout_id)
            if workout is None:
                self.db.add(Workout(uuid=workout_id, user_id=user_id, items=items, **fields))
                created += 1
            else:
                for key, value in fields.items():
                    setattr(workout, key, value)
                workout.items = items
                workout.updated_at = utcnow()
        await self.db.commit()
        return created, len(workouts) - created

    async def delete(self, user_id: int, workout_uuid: UUID) -> None:
        """Idempotent: deleting a missing workout is not an error."""
        workout = await self._find(workout_uuid)
        if workout is not None and workout.user_id == user_id:
            await self.db.delete(workout)
            await self.db.commit()
