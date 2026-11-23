"""Export everything of a user as one JSON document, and import such a
document (or workouts converted from other apps) back.

Importing is idempotent: workouts, exercises and weigh-ins keep their ids (or
get stable ones from `import_key`), so running the same import twice updates
instead of duplicating. Plans have no client ids; one whose name already exists
is skipped. Ids that belong to another account on this server (a backup of a
different account) are replaced with new, stable ones.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_weight import BodyWeight
from app.models.exercise import Exercise
from app.models.plan import Plan
from app.models.workout import Workout, utcnow
from app.schemas.backup import (
    BackupBodyWeight,
    BackupExercise,
    BackupIn,
    BackupOut,
    ImportResult,
)
from app.schemas.plan import PlanDayIn, PlanExerciseIn, PlanIn
from app.schemas.workout import WorkoutOut
from app.services.body_weight import BodyWeightService
from app.services.exercise import ExerciseService
from app.services.plan import PlanService
from app.services.workout import WorkoutService

IMPORT_NAMESPACE = uuid5(NAMESPACE_URL, "terminator/import")
SETTINGS = ("muscle_group", "log_type", "notes", "rep_min", "rep_max", "increment", "rest_seconds")


def _plan_in(plan: Plan) -> PlanIn:
    return PlanIn(
        name=plan.name,
        description=plan.description,
        is_public=plan.is_public,
        days=[
            PlanDayIn(
                name=day.name,
                exercises=[
                    PlanExerciseIn(
                        exercise_id=e.exercise_id,
                        exercise_name=e.exercise_name,
                        target_sets=e.target_sets,
                        target_reps_min=e.target_reps_min,
                        target_reps_max=e.target_reps_max,
                        superset=e.superset,
                    )
                    for e in day.exercises
                ],
            )
            for day in plan.days
        ],
    )


class BackupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def export(self, user_id: int) -> BackupOut:
        exercises = await ExerciseService(self.db).all(user_id)
        workouts = await WorkoutService(self.db).list_for_user(user_id, limit=None)
        plans = await PlanService(self.db).list_own(user_id)
        weights = await BodyWeightService(self.db).list(user_id, limit=None)
        return BackupOut(
            exported_at=datetime.now(UTC),
            exercises=[BackupExercise.model_validate(e, from_attributes=True) for e in exercises],
            workouts=[WorkoutOut.model_validate(w) for w in workouts],
            plans=[_plan_in(p) for p in plans],
            body_weights=[BackupBodyWeight.model_validate(b, from_attributes=True) for b in weights],
        )

    def _own_id(self, user_id: int, key: str) -> UUID:
        return uuid5(IMPORT_NAMESPACE, f"{user_id}:{key}")

    async def _foreign(self, model, ids: Sequence[UUID], user_id: int, id_column) -> set[UUID]:
        """Which of these ids another account already uses."""
        if not ids:
            return set()
        rows = await self.db.execute(select(id_column).where(id_column.in_(ids), model.user_id != user_id))
        return set(rows.scalars())

    async def import_backup(self, user_id: int, data: BackupIn) -> ImportResult:
        # Exercises first: workouts and plans refer to them. One that exists
        # (by id or name) keeps its own settings; only empty ones are filled in.
        exercise_ids = await self._import_exercises(user_id, data.exercises)
        created_exercises = sum(created for _, created in exercise_ids.values())
        remap = {old: new for old, (new, _) in exercise_ids.items()}

        # Workouts
        ids = [w.id for w in data.workouts if w.id]
        foreign = await self._foreign(Workout, ids, user_id, Workout.uuid)
        batch = []
        for w in data.workouts:
            if w.id and w.id not in foreign:
                workout_id = w.id
            elif w.id:
                workout_id = self._own_id(user_id, str(w.id))
            elif w.import_key:
                workout_id = self._own_id(user_id, w.import_key)
            else:
                workout_id = uuid4()
            items = [i.model_copy(update={"exercise_id": remap.get(i.exercise_id, i.exercise_id)}) for i in w.items]
            batch.append((workout_id, w.model_copy(update={"items": items})))
        created, updated = await WorkoutService(self.db).import_many(user_id, batch)

        # Plans (no client ids): skip names that exist
        plan_service = PlanService(self.db)
        taken = {p.name.strip().lower() for p in await plan_service.list_own(user_id)}
        plans_created = 0
        for plan in data.plans:
            if plan.name.strip().lower() in taken:
                continue
            days = [
                d.model_copy(
                    update={
                        "exercises": [
                            e.model_copy(update={"exercise_id": remap.get(e.exercise_id, e.exercise_id)})
                            for e in d.exercises
                        ]
                    }
                )
                for d in plan.days
            ]
            await plan_service.create(user_id, plan.model_copy(update={"days": days}))
            taken.add(plan.name.strip().lower())
            plans_created += 1

        weights = await self._import_body_weights(user_id, data.body_weights)
        # The steps above commit only when they have something to import: a
        # backup of exercises alone must not be left in a flushed transaction.
        await self.db.commit()
        return ImportResult(
            exercises_created=created_exercises,
            workouts_created=created,
            workouts_updated=updated,
            plans_created=plans_created,
            plans_skipped=len(data.plans) - plans_created,
            body_weights=weights,
        )

    async def _import_exercises(
        self, user_id: int, exercises: Sequence[BackupExercise]
    ) -> dict[UUID, tuple[UUID, bool]]:
        """old id -> (id here, created?)"""
        mine = await ExerciseService(self.db).all(user_id)
        by_id = {e.id: e for e in mine}
        by_name = {e.name.strip().lower(): e for e in mine}
        foreign = await self._foreign(Exercise, [e.id for e in exercises], user_id, Exercise.id)
        out: dict[UUID, tuple[UUID, bool]] = {}
        for e in exercises:
            target = by_id.get(e.id) or by_name.get(e.name.strip().lower())
            created = target is None
            if created:
                new_id = self._own_id(user_id, str(e.id)) if e.id in foreign else e.id
                target = Exercise(id=new_id, user_id=user_id, name=e.name)
                self.db.add(target)
                by_id[new_id] = target
                by_name[e.name.strip().lower()] = target
            for key in SETTINGS:
                if getattr(target, key) is None:
                    setattr(target, key, getattr(e, key))
            out[e.id] = (target.id, created)
        await self.db.flush()
        return out

    async def _import_body_weights(self, user_id: int, entries: Sequence[BackupBodyWeight]) -> int:
        if not entries:
            return 0
        ids = [e.id for e in entries]
        foreign = await self._foreign(BodyWeight, ids, user_id, BodyWeight.id)
        keyed = [(self._own_id(user_id, str(e.id)) if e.id in foreign else e.id, e) for e in entries]
        existing = {
            b.id: b
            for b in (
                await self.db.execute(select(BodyWeight).where(BodyWeight.id.in_([k for k, _ in keyed])))
            ).scalars()
        }
        for entry_id, e in keyed:
            row = existing.get(entry_id)
            if row is None:
                row = BodyWeight(id=entry_id, user_id=user_id)
                self.db.add(row)
                existing[entry_id] = row
            row.measured_at, row.weight, row.unit, row.body_fat = e.measured_at, e.weight, e.unit, e.body_fat
            row.updated_at = utcnow()
        await self.db.commit()
        return len(entries)
