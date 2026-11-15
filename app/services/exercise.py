"""The user's exercises: lookup by name, settings, stats and records, merging."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy import case, exists, func, select, update
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exercise import Exercise
from app.models.plan import PlanExercise
from app.models.workout import Workout, WorkoutItem, WorkoutSet, utcnow
from app.schemas.exercise import (
    ExerciseIn,
    ExerciseMergeResult,
    ExerciseOut,
    ExerciseProgress,
    ExerciseSession,
    SetRecord,
)
from app.schemas.workout import SetOut
from app.services.errors import Conflict, Invalid, NotFound

KG_PER_LB = 0.45359237
_HAS_SETS = exists().where(WorkoutSet.item_id == WorkoutItem.id)
# Weights are stored as entered; records compare them in kg.
_WEIGHT_KG = WorkoutSet.weight * case((WorkoutItem.weight_unit == "lb", KG_PER_LB), else_=1.0)
# Epley estimate; a single is the weight itself.
_E1RM = case((WorkoutSet.reps == 1, _WEIGHT_KG), else_=_WEIGHT_KG * (1 + WorkoutSet.reps / 30.0))

ExerciseRef = tuple[UUID | None, str]  # (id if the client knows it, name)


def _key(name: str) -> str:
    return name.strip().lower()


class ExerciseService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def all(self, user_id: int) -> Sequence[Exercise]:
        """The user's exercises (settings only, no stats)."""
        return (await self.db.execute(select(Exercise).where(Exercise.user_id == user_id))).scalars().all()

    async def _own(self, user_id: int, exercise_id: UUID) -> Exercise:
        exercise = await self.db.get(Exercise, exercise_id)
        if exercise is None or exercise.user_id != user_id:
            raise NotFound
        return exercise

    # ---- lookup -----------------------------------------------------------------

    async def resolve(self, user_id: int, refs: Sequence[ExerciseRef]) -> list[Exercise]:
        """The user's exercise for each (id, name): by id if it exists, else by
        name (ignoring case), else a new one (with the given id, if any).

        Matching by name makes uploads robust: a device that created "Squat"
        offline under its own id still lands on the existing "Squat". New
        exercises are added to the session; the caller commits.
        """
        mine = await self.all(user_id)
        by_id = {e.id: e for e in mine}
        by_name = {_key(e.name): e for e in mine}
        out = []
        for ref_id, name in refs:
            exercise = by_id.get(ref_id) if ref_id else None
            exercise = exercise or by_name.get(_key(name))
            if exercise is None:
                exercise = Exercise(id=ref_id or uuid4(), user_id=user_id, name=name.strip())
                self.db.add(exercise)
                by_name[_key(name)] = exercise
                by_id[exercise.id] = exercise
            out.append(exercise)
        return out

    # ---- reading ----------------------------------------------------------------

    async def list(self, user_id: int, ids: Sequence[UUID] | None = None) -> list[ExerciseOut]:
        """Exercises with when they were last done, their last sets and records."""
        stmt = select(Exercise).where(Exercise.user_id == user_id).order_by(func.lower(Exercise.name))
        if ids is not None:
            stmt = stmt.where(Exercise.id.in_(ids))
        exercises = (await self.db.execute(stmt)).scalars().all()
        if not exercises:
            return []
        ids = [e.id for e in exercises]
        last = await self._last_items(user_id, ids)
        times = await self._times(user_id, ids)
        sets = await self._sets_by_item([row.item_id for row in last.values()])
        best_weight = await self._best(user_id, ids, (_WEIGHT_KG.desc(), WorkoutSet.reps.desc()), WorkoutSet.weight > 0)
        best_e1rm = await self._best(
            user_id, ids, (_E1RM.desc(), WorkoutSet.reps.desc()), WorkoutSet.weight > 0, WorkoutSet.reps <= 12
        )
        best_reps = await self._best(user_id, ids, (WorkoutSet.reps.desc(), _WEIGHT_KG.desc()))
        out = []
        for e in exercises:
            out_item = ExerciseOut.model_validate(e)
            if row := last.get(e.id):
                out_item = out_item.model_copy(
                    update={
                        "times_performed": times.get(e.id, 0),
                        "last_performed_at": row.performed_at,
                        "last_unit": row.weight_unit,
                        "last_sets": sets.get(row.item_id, []),
                        "best_weight": best_weight.get(e.id),
                        "best_e1rm": best_e1rm.get(e.id),
                        "best_reps": best_reps.get(e.id),
                    }
                )
            out.append(out_item)
        return out

    async def get(self, user_id: int, exercise_id: UUID) -> ExerciseOut:
        found = await self.list(user_id, [exercise_id])
        if not found:
            raise NotFound
        return found[0]

    async def _last_items(self, user_id: int, ids: Sequence[UUID]) -> dict:
        ranked = (
            select(
                WorkoutItem.id.label("item_id"),
                WorkoutItem.exercise_id,
                WorkoutItem.weight_unit,
                Workout.performed_at,
                func.row_number()
                .over(
                    partition_by=WorkoutItem.exercise_id,
                    order_by=(Workout.performed_at.desc(), WorkoutItem.id.desc()),
                )
                .label("rn"),
            )
            .join(Workout)
            .where(Workout.user_id == user_id, WorkoutItem.exercise_id.in_(ids), _HAS_SETS)
            .subquery()
        )
        rows = await self.db.execute(select(ranked).where(ranked.c.rn == 1))
        return {row.exercise_id: row for row in rows}

    async def _times(self, user_id: int, ids: Sequence[UUID]) -> dict[UUID, int]:
        """In how many workouts each exercise was done (an exercise can appear
        twice in one workout, e.g. after merging two)."""
        rows = await self.db.execute(
            select(WorkoutItem.exercise_id, func.count(WorkoutItem.workout_id.distinct()))
            .join(Workout)
            .where(Workout.user_id == user_id, WorkoutItem.exercise_id.in_(ids), _HAS_SETS)
            .group_by(WorkoutItem.exercise_id)
        )
        return {exercise_id: count for exercise_id, count in rows}

    async def _best(self, user_id: int, ids: Sequence[UUID], order_by: tuple, *where) -> dict[UUID, SetRecord]:
        """The top working set per exercise by `order_by` (earliest one on a tie)."""
        stmt = (
            select(
                WorkoutItem.exercise_id,
                WorkoutSet.weight,
                WorkoutSet.reps,
                WorkoutItem.weight_unit,
                Workout.performed_at,
                Workout.uuid,
            )
            .select_from(WorkoutSet)
            .join(WorkoutItem, WorkoutSet.item_id == WorkoutItem.id)
            .join(Workout, WorkoutItem.workout_id == Workout.id)
            .where(
                Workout.user_id == user_id,
                WorkoutItem.exercise_id.in_(ids),
                WorkoutSet.reps > 0,
                WorkoutSet.kind != "warmup",
                *where,
            )
            .ext(distinct_on(WorkoutItem.exercise_id))
            .order_by(WorkoutItem.exercise_id, *order_by, Workout.performed_at)
        )
        return {
            r.exercise_id: SetRecord(
                weight=r.weight,
                reps=r.reps,
                weight_unit=r.weight_unit,
                performed_at=r.performed_at,
                workout_id=r.uuid,
            )
            for r in await self.db.execute(stmt)
        }

    async def _sets_by_item(self, item_ids: Sequence[int]) -> dict[int, list[SetOut]]:
        out: dict[int, list[SetOut]] = {}
        if not item_ids:
            return out
        rows = await self.db.execute(
            select(WorkoutSet)
            .where(WorkoutSet.item_id.in_(item_ids))
            .order_by(WorkoutSet.item_id, WorkoutSet.order)
        )
        for s in rows.scalars():
            out.setdefault(s.item_id, []).append(SetOut.model_validate(s))
        return out

    async def progress(self, user_id: int, exercise_id: UUID, limit: int = 1000) -> ExerciseProgress:
        """Every logged session of one exercise, oldest first (the most recent `limit`)."""
        exercise = await self._own(user_id, exercise_id)
        rows = (
            await self.db.execute(
                select(WorkoutItem.id, WorkoutItem.weight_unit, Workout.uuid, Workout.performed_at)
                .join(Workout)
                .where(Workout.user_id == user_id, WorkoutItem.exercise_id == exercise_id, _HAS_SETS)
                .order_by(Workout.performed_at.desc(), WorkoutItem.id.desc())
                .limit(limit)
            )
        ).all()
        sets = await self._sets_by_item([r.id for r in rows])
        return ExerciseProgress(
            exercise_id=exercise.id,
            exercise_name=exercise.name,
            sessions=[
                ExerciseSession(
                    workout_id=r.uuid, performed_at=r.performed_at, weight_unit=r.weight_unit, sets=sets.get(r.id, [])
                )
                for r in reversed(rows)
            ],
        )

    # ---- changes ------------------------------------------------------------------

    async def _touch_workouts_using(self, exercise_ids: Sequence[UUID]) -> list[int]:
        """Bump `updated_at` of workouts that show these exercises, so clients
        refresh their cached copies (which carry the exercise name)."""
        workout_ids = (
            (
                await self.db.execute(
                    select(WorkoutItem.workout_id).where(WorkoutItem.exercise_id.in_(exercise_ids)).distinct()
                )
            )
            .scalars()
            .all()
        )
        if workout_ids:
            await self.db.execute(
                update(Workout)
                .where(Workout.id.in_(workout_ids))
                .values(updated_at=utcnow())
                .execution_options(synchronize_session=False)
            )
        return list(workout_ids)

    async def upsert(self, user_id: int, exercise_id: UUID, data: ExerciseIn) -> tuple[ExerciseOut, bool]:
        """Create or replace an exercise. Returns (exercise, created).
        Raises Conflict when another exercise already has the name."""
        exercise = await self.db.get(Exercise, exercise_id)
        if exercise is not None and exercise.user_id != user_id:
            raise NotFound
        clash = next((e for e in await self.all(user_id) if _key(e.name) == _key(data.name)), None)
        if clash is not None and clash.id != exercise_id:
            raise Conflict(f'"{clash.name}" already exists', existing_id=clash.id)

        created = exercise is None
        if created:
            exercise = Exercise(id=exercise_id, user_id=user_id)
            self.db.add(exercise)
        renamed = not created and exercise.name != data.name
        for key, value in data.model_dump().items():
            setattr(exercise, key, value)
        exercise.updated_at = utcnow()
        if renamed:
            await self._touch_workouts_using([exercise_id])
        await self.db.commit()
        return await self.get(user_id, exercise_id), created

    async def merge(self, user_id: int, source_id: UUID, target_id: UUID) -> ExerciseMergeResult:
        """Move all of `source`'s history and plan entries to `target`, then delete
        `source`. Settings `target` lacks are taken from `source`."""
        source = await self._own(user_id, source_id)
        target = await self._own(user_id, target_id)
        if source_id == target_id:
            raise Invalid("Can't merge an exercise into itself")

        workout_ids = await self._touch_workouts_using([source_id])
        await self.db.execute(
            update(WorkoutItem)
            .where(WorkoutItem.exercise_id == source_id)
            .values(exercise_id=target_id)
            .execution_options(synchronize_session=False)
        )
        plan_result = await self.db.execute(
            update(PlanExercise)
            .where(PlanExercise.exercise_id == source_id)
            .values(exercise_id=target_id)
            .execution_options(synchronize_session=False)
        )
        for key in ("muscle_group", "notes", "rep_min", "rep_max", "increment", "rest_seconds"):
            if getattr(target, key) is None:
                setattr(target, key, getattr(source, key))
        target.updated_at = utcnow()
        await self.db.delete(source)
        await self.db.commit()
        return ExerciseMergeResult(workouts=len(workout_ids), plan_exercises=plan_result.rowcount)

    async def delete(self, user_id: int, exercise_id: UUID) -> None:
        """Delete an exercise nothing uses (idempotent). Raises Conflict when used."""
        exercise = await self.db.get(Exercise, exercise_id)
        if exercise is None or exercise.user_id != user_id:
            return
        used = await self.db.scalar(
            select(
                exists().where(WorkoutItem.exercise_id == exercise_id)
                | exists().where(PlanExercise.exercise_id == exercise_id)
            )
        )
        if used:
            raise Conflict("The exercise is used in workouts or plans; merge it into another one instead")
        await self.db.delete(exercise)
        await self.db.commit()
