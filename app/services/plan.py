from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exercise import Exercise
from app.models.plan import Plan, PlanDay, PlanExercise
from app.models.user import User
from app.schemas.plan import PlanDayIn, PlanIn
from app.services.errors import NotFound
from app.services.exercise import ExerciseService

_LOAD_DAYS = selectinload(Plan.days).selectinload(PlanDay.exercises)


def _build_exercises(day_in: PlanDayIn, exercises: dict[tuple, Exercise]) -> list[PlanExercise]:
    return [
        PlanExercise(
            exercise=exercises[(ex.exercise_id, ex.exercise_name)],
            target_sets=ex.target_sets,
            target_reps_min=ex.target_reps_min,
            target_reps_max=ex.target_reps_max,
            superset=ex.superset,
            order=i,
        )
        for i, ex in enumerate(day_in.exercises)
    ]


class PlanService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_own(self, user_id: int) -> Sequence[Plan]:
        stmt = (
            select(Plan)
            .where(Plan.creator_id == user_id)
            .options(_LOAD_DAYS)
            .order_by(Plan.id.desc())
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def get_visible(self, user_id: int, plan_id: int) -> Plan:
        stmt = (
            select(Plan)
            .where(Plan.id == plan_id, or_(Plan.creator_id == user_id, Plan.is_public))
            .options(_LOAD_DAYS)
            .execution_options(populate_existing=True)
        )
        plan = (await self.db.execute(stmt)).scalar_one_or_none()
        if plan is None:
            raise NotFound
        return plan

    async def _get_own(self, user_id: int, plan_id: int) -> Plan:
        plan = await self.get_visible(user_id, plan_id)
        if plan.creator_id != user_id:
            raise NotFound
        return plan

    async def _resolve(self, user_id: int, data: PlanIn) -> dict[tuple, Exercise]:
        refs = list(dict.fromkeys((ex.exercise_id, ex.exercise_name) for d in data.days for ex in d.exercises))
        return dict(zip(refs, await ExerciseService(self.db).resolve(user_id, refs), strict=True))

    async def create(self, user_id: int, data: PlanIn) -> Plan:
        exercises = await self._resolve(user_id, data)
        plan = Plan(
            creator_id=user_id,
            name=data.name,
            description=data.description,
            is_public=data.is_public,
            days=[
                PlanDay(name=d.name, order=i, exercises=_build_exercises(d, exercises))
                for i, d in enumerate(data.days)
            ],
        )
        self.db.add(plan)
        await self.db.commit()
        return await self.get_visible(user_id, plan.id)

    async def update(self, user_id: int, plan_id: int, data: PlanIn) -> Plan:
        plan = await self._get_own(user_id, plan_id)
        exercises = await self._resolve(user_id, data)
        plan.name = data.name
        plan.description = data.description
        plan.is_public = data.is_public

        # Update days in place by position so day ids stay stable; logged
        # workouts point at them to work out the "next day" of a plan.
        days = list(plan.days)
        for i, day_in in enumerate(data.days):
            if i < len(days):
                day = days[i]
                day.name, day.order = day_in.name, i
                day.exercises = _build_exercises(day_in, exercises)
            else:
                days.append(PlanDay(name=day_in.name, order=i, exercises=_build_exercises(day_in, exercises)))
        plan.days = days[: len(data.days)]

        await self.db.commit()
        return await self.get_visible(user_id, plan_id)

    async def delete(self, user_id: int, plan_id: int) -> None:
        plan = await self._get_own(user_id, plan_id)
        await self.db.delete(plan)
        await self.db.commit()

    async def set_active(self, user: User, plan_id: int | None) -> None:
        if plan_id is not None:
            await self.get_visible(user.id, plan_id)
        user.active_plan_id = plan_id
        await self.db.commit()

    async def is_day_visible(self, user_id: int, day_id: int) -> bool:
        stmt = (
            select(PlanDay.id)
            .join(Plan)
            .where(PlanDay.id == day_id, or_(Plan.creator_id == user_id, Plan.is_public))
        )
        return (await self.db.execute(stmt)).scalar_one_or_none() is not None
