from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from constants.error import ClientError
from controllers.models import ExerciseTypeModel, UpsertExerciseTypeModel
from database import get_tx
from database.models.exercise_type import ExerciseType
from utils import AuthAPIRouter
from utils.exceptions import BadRequestException


router_with_auth = AuthAPIRouter(
    prefix="/exercise/type",
    tags=["Exercise"],
)


@router_with_auth.get("s", response_model=list[ExerciseTypeModel])
def get_exercises(tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        return ExerciseType.get_all(session)


@router_with_auth.post("", response_model=list[ExerciseTypeModel])
def create_exercise(body: UpsertExerciseTypeModel, tx: sessionmaker = Depends(get_tx)):
    try:
        with tx.begin() as session:
            ExerciseType.create(session, body.exercise_name)
            return ExerciseType.get_all(session)

    except IntegrityError as e:
        raise BadRequestException(
            error_code=ClientError.DATABASE_INTEGRITY_ERROR,
        )


@router_with_auth.delete("", response_model=list[ExerciseTypeModel])
def delete_exercise(id: int, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        ExerciseType.delete_by_id(session, id)
        return ExerciseType.get_all(session)


@router_with_auth.patch("", response_model=list[ExerciseTypeModel])
def update_exercise(id: int, body: UpsertExerciseTypeModel, tx: sessionmaker = Depends(get_tx)):
    try:
        with tx.begin() as session:
            ExerciseType.update(session, id, body.exercise_name)
            return ExerciseType.get_all(session)

    except IntegrityError as e:
        raise BadRequestException(
            error_code=ClientError.DATABASE_INTEGRITY_ERROR,
        )
