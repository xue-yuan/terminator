from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.workout import Workout
from app.schemas.plan import PlanOut
from app.schemas.user import Summary
from app.services.errors import NotFound
from app.services.plan import PlanService


def week_streak(active_weeks: set[date], this_week: date) -> int:
    """Consecutive weeks with a workout, counting back from this week (or last
    week, if nothing has been logged yet this week)."""
    week = this_week if this_week in active_weeks else this_week - timedelta(weeks=1)
    streak = 0
    while week in active_weeks:
        streak += 1
        week -= timedelta(weeks=1)
    return streak


class SummaryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def summary(self, user: User, tz: ZoneInfo, now: datetime | None = None) -> Summary:
        now = (now or datetime.now(tz)).astimezone(tz)
        this_week = now.date() - timedelta(days=now.weekday())
        week_start = datetime.combine(this_week, time.min, tzinfo=tz)

        mine = Workout.user_id == user.id
        total = await self.db.scalar(select(func.count()).select_from(Workout).where(mine))
        this_week_count = await self.db.scalar(
            select(func.count()).select_from(Workout).where(mine, Workout.performed_at >= week_start)
        )
        local_week = cast(
            func.date_trunc("week", func.timezone(tz.key, Workout.performed_at)), Date
        )
        weeks = (await self.db.execute(select(local_week).where(mine).distinct())).scalars()

        active_plan, next_day_id = await self._active_plan(user)
        return Summary(
            total_workouts=total or 0,
            workouts_this_week=this_week_count or 0,
            week_streak=week_streak(set(weeks), this_week),
            active_plan=active_plan,
            next_plan_day_id=next_day_id,
        )

    async def _active_plan(self, user: User) -> tuple[PlanOut | None, int | None]:
        if user.active_plan_id is None:
            return None, None
        try:
            plan = await PlanService(self.db).get_visible(user.id, user.active_plan_id)
        except NotFound:  # plan was made private by its owner
            return None, None
        if not plan.days:
            return PlanOut.model_validate(plan).model_copy(update={"is_active": True}), None

        day_ids = [d.id for d in plan.days]
        last_day = await self.db.scalar(
            select(Workout.plan_day_id)
            .where(Workout.user_id == user.id, Workout.plan_day_id.in_(day_ids))
            .order_by(Workout.performed_at.desc())
            .limit(1)
        )
        next_id = day_ids[(day_ids.index(last_day) + 1) % len(day_ids)] if last_day is not None else day_ids[0]
        return PlanOut.model_validate(plan).model_copy(update={"is_active": True}), next_id
