from enum import Enum

from pydantic import BaseModel


class TokenModel(BaseModel):
    token: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidXNlci03ODNiMWU3ZmRjMWY0ZWZlYWY0YmJmNmY5MDM3NTU3OCIsImV4cCI6MTcwMzIzODU0OX0.K-R5VtVC-zA52d0Nm8haCDXlp_6slsF9-oPQevyhXF8"


class AuthModel(BaseModel):
    username: str = "username"
    password: str = "password"


class SetModel(BaseModel):
    repetition: int = 12
    weight: float = 50.5


class ExerciseModel(BaseModel):
    exercise_type_id: int = 1
    sets: list[SetModel]


class WorkoutModel(BaseModel):
    datetime: str = "2020-02-02T00:00:00+08:00"
    exercises: list[ExerciseModel]


class GetWorkoutModel(WorkoutModel):
    workout_id: str = "workout-ae5f9c1304804ec08df8d68c9d75a54f"


class OrderEnum(str, Enum):
    asc = "asc"
    desc = "desc"


class QueryModel(BaseModel):
    limit: int = 50
    offset: int = 0
    sort: str = None
    order: OrderEnum = OrderEnum.desc


class DateModel(BaseModel):
    from_date: str = "2020-01-01"
    to_date: str = "2025-01-01"


class UserModel(BaseModel):
    user_id: str = "user-0b4d2552bff241cd8edff0dac909f92b"
    username: str = "username"


class ExerciseTypeModel(BaseModel):
    exercise_type_id: int = 1
    exercise_name: str = "example activity name"


class UpsertExerciseTypeModel(BaseModel):
    exercise_name: str = "test"
