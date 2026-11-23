from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.schemas.common import WeightUnit


class BodyWeightIn(BaseModel):
    measured_at: AwareDatetime
    weight: float = Field(gt=0, le=1000)
    unit: WeightUnit
    body_fat: float | None = Field(default=None, ge=2, le=70)  # percent


class BodyWeightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    measured_at: datetime
    weight: float
    unit: WeightUnit
    body_fat: float | None
    updated_at: datetime
