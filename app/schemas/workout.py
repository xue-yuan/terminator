from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.common import Name, OptionalText, PrKind, SetKind, Superset, WeightUnit


class WorkoutSetIn(BaseModel):
    reps: int = Field(ge=0, le=1000)
    weight: float = Field(ge=0, le=2000)  # 0 = bodyweight
    rpe: float | None = Field(default=None, ge=1, le=10)
    kind: SetKind = "working"
    duration_seconds: int | None = Field(default=None, ge=0, le=24 * 3600)
    distance_m: float | None = Field(default=None, ge=0, le=1_000_000)


class WorkoutItemIn(BaseModel):
    # The exercise's id when the client knows it; otherwise (or if the id is
    # unknown to the server) the exercise is found by name, or created.
    exercise_id: UUID | None = None
    exercise_name: Name
    weight_unit: WeightUnit = "kg"
    superset: Superset = None
    sets: list[WorkoutSetIn] = Field(default_factory=list, max_length=100)


class WorkoutIn(BaseModel):
    """Full workout document. Item/set order is the list order."""

    name: OptionalText = None
    performed_at: AwareDatetime
    duration_seconds: int | None = Field(default=None, ge=0, le=24 * 3600)
    notes: OptionalText = None
    plan_day_id: int | None = None
    items: list[WorkoutItemIn] = Field(default_factory=list, max_length=50)


class WorkoutCreate(WorkoutIn):
    id: UUID | None = None


class SetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reps: int
    weight: float
    rpe: float | None
    kind: SetKind
    duration_seconds: int | None = None
    distance_m: float | None = None


class WorkoutSetOut(SetOut):
    # Records this set broke when it was done (app/services/records.py).
    pr: list[PrKind] = []


class WorkoutItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    exercise_id: UUID
    exercise_name: str
    weight_unit: WeightUnit
    superset: int | None
    sets: list[WorkoutSetOut]


class WorkoutOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(validation_alias="uuid")
    name: str | None
    performed_at: datetime
    duration_seconds: int | None
    notes: str | None
    plan_day_id: int | None
    items: list[WorkoutItemOut]
    created_at: datetime
    updated_at: datetime


class WorkoutActivity(BaseModel):
    """A workout reduced to what a calendar needs: small enough to cache all of them."""

    id: UUID
    performed_at: datetime
    name: str | None
    duration_seconds: int | None
    sets: int  # working sets (warm-ups don't count)
