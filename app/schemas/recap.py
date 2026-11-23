from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import PrKind, WeightUnit

Period = Literal["week", "month"]


class RecapTotals(BaseModel):
    workouts: int = 0
    duration_seconds: int = 0  # of the workouts that have one
    working_sets: int = 0
    reps: int = 0
    volume_kg: float = 0.0  # weight × reps of working sets
    distance_m: float = 0.0  # cardio
    cardio_seconds: int = 0  # timed and cardio sets


class RecapRecord(BaseModel):
    """A set that broke a record, and which ones."""

    exercise_id: UUID
    exercise_name: str
    kinds: list[PrKind]
    weight: float
    reps: int
    weight_unit: WeightUnit
    duration_seconds: int | None
    distance_m: float | None
    performed_at: datetime
    workout_id: UUID


class RecapExercise(BaseModel):
    exercise_id: UUID
    exercise_name: str
    sets: int  # working sets
    volume_kg: float


class RecapUnlock(BaseModel):
    achievement: str
    icon: str
    title: str
    medal: str
    unlocked_at: datetime


class RecapOut(BaseModel):
    """A week (Monday to Sunday) or calendar month of training, in the asked time zone."""

    period: Period
    start: date
    end: date  # the day after the last one
    totals: RecapTotals
    previous: RecapTotals  # the period before, to compare with
    days: list[date]  # days with a workout
    records: list[RecapRecord]
    exercises: list[RecapExercise]  # most working sets first
    muscles: dict[str, int]  # working sets per muscle group
    xp: int  # banked by the period's workouts
    unlocks: list[RecapUnlock]  # tiers reached in the period, oldest first
