from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.schemas.common import Name
from app.schemas.exercise import MuscleGroup


def _blank_to_none(value: object) -> object:
    """Trim; collapse runs of spaces (aka is space-separated); "" means none."""
    if isinstance(value, str):
        value = " ".join(value.split())
        return value or None
    return value


def _optional(max_length: int):
    return Annotated[
        Annotated[str, StringConstraints(max_length=max_length)] | None, BeforeValidator(_blank_to_none)
    ]


class CatalogIn(BaseModel):
    """An entry of the built-in exercise library (admins only)."""

    name: Name
    zh: _optional(100) = None
    aka: _optional(300) = None
    muscle_group: MuscleGroup


class CatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    zh: str | None
    aka: str | None
    muscle_group: MuscleGroup
