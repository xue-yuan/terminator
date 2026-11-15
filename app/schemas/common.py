from typing import Annotated, Literal

from pydantic import Field, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)] | None

WeightUnit = Literal["kg", "lb"]
# Warm-up sets don't count towards volume, set counts or records.
SetKind = Literal["working", "warmup"]
# Which record a set broke (see app/services/records.py).
PrKind = Literal["weight", "e1rm", "reps"]
# Group number shared by consecutive exercises done as a superset.
Superset = Annotated[int, Field(ge=1, le=50)] | None
