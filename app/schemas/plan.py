from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import Name, OptionalText, Superset


class PlanExerciseIn(BaseModel):
    exercise_id: UUID | None = None  # found by name (or created) when missing or unknown
    exercise_name: Name
    target_sets: int | None = Field(default=3, ge=1, le=20)
    target_reps_min: int | None = Field(default=8, ge=1, le=100)
    target_reps_max: int | None = Field(default=12, ge=1, le=100)
    superset: Superset = None

    @model_validator(mode="after")
    def _reps_range(self) -> "PlanExerciseIn":
        lo, hi = self.target_reps_min, self.target_reps_max
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("target_reps_min must be <= target_reps_max")
        return self


class PlanDayIn(BaseModel):
    name: Name
    exercises: list[PlanExerciseIn] = Field(default_factory=list, max_length=30)


class PlanIn(BaseModel):
    """Full plan document. Day/exercise order is the list order."""

    name: Name
    description: OptionalText = None
    is_public: bool = False
    days: list[PlanDayIn] = Field(default_factory=list, max_length=14)


class PlanExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    exercise_id: UUID
    exercise_name: str
    target_sets: int | None
    target_reps_min: int | None
    target_reps_max: int | None
    superset: int | None


class PlanDayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    exercises: list[PlanExerciseOut]


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    creator_id: int
    name: str
    description: str | None
    is_public: bool
    days: list[PlanDayOut]
    is_active: bool = False
