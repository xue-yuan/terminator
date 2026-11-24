from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import LogType, Name, OptionalText, WeightUnit
from app.schemas.workout import SetOut

MuscleGroup = Literal[
    "chest",
    "lats",
    "upper_back",
    "lower_back",
    "front_delts",
    "side_delts",
    "rear_delts",
    "biceps",
    "triceps",
    "quads",
    "hamstrings",
    "glutes",
    "calves",
    "core",
    "cardio",
    "other",
]

# Groups that were split later: "arms" into biceps and triceps (migration
# e1f3b5c7a9d2), then "back", "legs" and "shoulders" into the muscles below
# (b8c4e7f1a2d6). The migrations filed existing rows with these same rules;
# older app versions and backups still send the old names, and the exercise's
# name says where it goes. Per old group: (new group, words in the name) tried
# in order, then the fallback.
LEGACY_GROUPS: dict[str, tuple[list[tuple[str, tuple[str, ...]]], str]] = {
    "arms": (
        [
            ("triceps", ("tricep", "pushdown", "push-down", "skull", "extension", "kickback", "close-grip", "dip", "三頭", "下壓", "伸展", "窄握", "撐體")),
            ("biceps", ("curl", "bicep", "彎舉", "二頭")),
        ],
        "other",
    ),
    "back": (
        [
            ("rear_delts", ("face pull", "facepull", "rear delt", "臉拉", "後三角")),
            ("lower_back", ("deadlift", "rack pull", "back extension", "hyperextension", "good morning", "硬舉", "背伸展", "山羊挺身", "羅馬椅", "下背", "早安")),
            ("lats", ("pull-up", "pullup", "pull up", "chin-up", "chinup", "chin up", "pulldown", "pull-down", "pull down", "lat pull", "lats", "pullover", "引體", "下拉", "背闊", "直臂")),
        ],
        "upper_back",
    ),
    "shoulders": (
        [
            ("rear_delts", ("rear", "reverse fly", "reverse pec", "face pull", "後三角", "反向飛鳥", "臉拉", "後束")),
            ("side_delts", ("lateral", "side raise", "upright", "y raise", "側平舉", "側三角", "直立划船", "側束")),
        ],
        "front_delts",
    ),
    "legs": (
        [
            ("calves", ("calf", "calves", "提踵", "小腿")),
            ("hamstrings", ("romanian", "rdl", "leg curl", "hamstring", "glute-ham", "nordic", "good morning", "stiff-leg", "stiff leg", "腿彎舉", "腿後", "羅馬尼亞", "直腿", "早安")),
            ("glutes", ("hip thrust", "glute", "abduct", "adduct", "kickback", "sumo", "bridge", "臀", "外展", "內收", "相撲", "髖")),
        ],
        "quads",
    ),
}


def legacy_group(old: str, *names: str | None) -> str:
    """Where an exercise once filed under an old group (arms, back, legs, shoulders) goes now."""
    rules, fallback = LEGACY_GROUPS[old]
    text = " ".join(n for n in names if n).lower()
    return next((group for group, words in rules if any(word in text for word in words)), fallback)


def file_legacy_group(value: object, info: ValidationInfo) -> object:
    """A field validator (mode="before") for muscle_group: an old group becomes the muscle it now is."""
    if value not in LEGACY_GROUPS:
        return value
    return legacy_group(value, info.data.get("name"), info.data.get("zh"), info.data.get("aka"))

Reps = Annotated[int, Field(ge=1, le=100)] | None


class ExerciseIn(BaseModel):
    """Create or replace an exercise's name and settings."""

    name: Name
    muscle_group: MuscleGroup | None = None
    log_type: LogType | None = None  # None: the library's for this name, else weight × reps
    notes: OptionalText = None
    rep_min: Reps = None
    rep_max: Reps = None
    increment: Annotated[float, Field(gt=0, le=50)] | None = None
    rest_seconds: Annotated[int, Field(ge=0, le=1800)] | None = None

    _legacy = field_validator("muscle_group", mode="before")(file_legacy_group)

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
    duration_seconds: int | None = None
    distance_m: float | None = None
    performed_at: datetime
    workout_id: UUID


class ExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    muscle_group: MuscleGroup | None
    log_type: LogType | None
    notes: str | None
    rep_min: int | None
    rep_max: int | None

    _legacy = field_validator("muscle_group", mode="before")(file_legacy_group)
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
    best_reps: SetRecord | None = None  # most reps in one bodyweight set (weight 0)
    best_duration: SetRecord | None = None  # longest set without a distance (a plank)
    best_distance: SetRecord | None = None  # longest distance in one set (a run)


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
