"""Backup format: everything of one user, as JSON. Exported by GET /export,
read back by POST /import (also used for workouts converted from other apps'
CSV files by the frontend)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.body_weight import BodyWeightIn
from app.schemas.exercise import ExerciseIn
from app.schemas.plan import PlanIn
from app.schemas.workout import WorkoutIn, WorkoutOut

FORMAT = "terminator-backup"
VERSION = 1


class BackupExercise(ExerciseIn):
    id: UUID


class BackupBodyWeight(BodyWeightIn):
    id: UUID


class ImportWorkout(WorkoutIn):
    """A workout to import. Without an id, `import_key` (e.g. source + date +
    name) gives it a stable one, so importing the same file again updates
    instead of duplicating."""

    id: UUID | None = None
    import_key: str | None = Field(default=None, max_length=300)


class BackupOut(BaseModel):
    format: Literal["terminator-backup"] = FORMAT
    version: int = VERSION
    exported_at: datetime
    exercises: list[BackupExercise]
    workouts: list[WorkoutOut]
    plans: list[PlanIn]
    body_weights: list[BackupBodyWeight]


class BackupIn(BaseModel):
    format: Literal["terminator-backup"] | None = None
    version: int | None = Field(default=None, ge=1, le=VERSION)
    exercises: list[BackupExercise] = Field(default_factory=list, max_length=5000)
    workouts: list[ImportWorkout] = Field(default_factory=list, max_length=2000)
    plans: list[PlanIn] = Field(default_factory=list, max_length=200)
    body_weights: list[BackupBodyWeight] = Field(default_factory=list, max_length=10000)


class ImportResult(BaseModel):
    exercises_created: int
    workouts_created: int
    workouts_updated: int
    plans_created: int
    plans_skipped: int  # a plan with that name already exists
    body_weights: int
