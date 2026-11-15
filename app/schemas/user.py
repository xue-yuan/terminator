from pydantic import BaseModel, ConfigDict

from app.schemas.plan import PlanOut


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str | None
    is_admin: bool = False  # in ADMIN_EMAILS: may manage who uses the app


class Summary(BaseModel):
    total_workouts: int
    workouts_this_week: int
    # Consecutive ISO weeks (Mon-Sun, in the caller's time zone) with at least
    # one workout. The current week doesn't break the streak until it's over.
    week_streak: int
    active_plan: PlanOut | None
    next_plan_day_id: int | None
