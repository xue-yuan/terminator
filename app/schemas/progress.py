from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TierOut(BaseModel):
    target: float
    medal: str
    xp: int
    # None for a hidden achievement nobody has earned yet.
    title: str | None
    description: str | None
    unlocked_at: datetime | None
    workout_id: UUID | None  # the workout that reached it, if one did


class AchievementOut(BaseModel):
    id: str
    category: str
    name: str | None  # None while hidden
    icon: str
    metric: str  # what value counts (sets, kg, a ratio...), for showing it
    hidden: bool
    value: float  # where you are now (0 while hidden)
    tiers: list[TierOut]


class TitleOut(BaseModel):
    key: str  # "<achievement>:<target>"
    title: str
    medal: str


class TitleIn(BaseModel):
    title: str | None = Field(max_length=60)


class Category(BaseModel):
    id: str
    name: str


class ProgressOut(BaseModel):
    xp: int
    level: int
    level_xp: int  # total XP this level started at
    next_level_xp: int  # total XP the next level starts at
    title: TitleOut | None
    # How XP is earned (app/services/achievements.py), so a device can work out
    # a finished workout's XP before it's uploaded.
    rules: dict[str, int]
    categories: list[Category]
    achievements: list[AchievementOut]
