from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Name, OptionalText, WeightUnit
from app.schemas.workout import SetOut

MuscleGroup = Literal["chest", "back", "legs", "shoulders", "arms", "core", "other"]
Reps = Annotated[int, Field(ge=1, le=100)] | None


class ExerciseIn(BaseModel):
    """Create or replace an exercise's name and settings."""

    name: Name
    muscle_group: MuscleGroup | None = None
    notes: OptionalText = None
    rep_min: Reps = None
    rep_max: Reps = None
    increment: Annotated[float, Field(gt=0, le=50)] | None = None
    rest_seconds: Annotated[int, Field(ge=0, le=1800)] | None = None

    @model_validator(mode="after")
    def _reps_range(self) -> "ExerciseIn":
        if self.rep_min is not None and self.rep_max is not None and self.rep_min > self.rep_max:
            raise ValueError("rep_min must be <= rep_max")
        return self


class SetRecord(BaseModel):
    """One logged set, with where it happened."""

    weight: float
    reps: int
    weight_unit: WeightUnit
    performed_at: datetime
    workout_id: UUID


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    muscle_group: MuscleGroup | None
    notes: str | None
    rep_min: int | None
    rep_max: int | None
    increment: float | None
    rest_seconds: int | None
    updated_at: datetime

    times_performed: int = 0
    last_performed_at: datetime | None = None
    last_unit: WeightUnit | None = None
    last_sets: list[SetOut] = []
    # Records over all logged working sets (not warm-ups); weights are compared in kg.
    best_weight: SetRecord | None = None  # heaviest set
    best_e1rm: SetRecord | None = None  # highest estimated 1RM (sets of 1-12 reps)
    best_reps: SetRecord | None = None  # most reps in one set


class ExerciseSession(BaseModel):
    """One workout's sets of a single exercise."""

    workout_id: UUID
    performed_at: datetime
    weight_unit: WeightUnit
    sets: list[SetOut]


class ExerciseProgress(BaseModel):
    exercise_id: UUID
    exercise_name: str
    sessions: list[ExerciseSession]  # oldest first


class ExerciseMerge(BaseModel):
    into: UUID


class ExerciseMergeResult(BaseModel):
    workouts: int
    plan_exercises: int
