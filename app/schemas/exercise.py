from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import Name, OptionalText, WeightUnit
from app.schemas.workout import SetOut

MuscleGroup = Literal["chest", "back", "legs", "shoulders", "biceps", "triceps", "core", "other"]

# "arms" was one group until biceps and triceps were split (migration
# e1f3b5c7a9d2, which files existing rows the same way). Older app versions and
# backups still send it: the exercise's name says which one it is.
_TRICEPS = ("tricep", "pushdown", "push-down", "skull", "extension", "kickback", "close-grip", "dip", "三頭", "下壓", "伸展", "窄握", "撐體")
_BICEPS = ("curl", "bicep", "彎舉", "二頭")


def arms_group(*names: str | None) -> str:
    """Biceps or triceps for an exercise once filed under "arms" (other if neither fits)."""
    text = " ".join(n for n in names if n).lower()
    if any(word in text for word in _TRICEPS):
        return "triceps"
    if any(word in text for word in _BICEPS):
        return "biceps"
    return "other"


def file_legacy_arms(value: object, info: ValidationInfo) -> object:
    """A field validator (mode="before") for muscle_group: "arms" becomes biceps or triceps."""
    if value != "arms":
        return value
    return arms_group(info.data.get("name"), info.data.get("zh"), info.data.get("aka"))

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

    _arms = field_validator("muscle_group", mode="before")(file_legacy_arms)

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

    _arms = field_validator("muscle_group", mode="before")(file_legacy_arms)
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
