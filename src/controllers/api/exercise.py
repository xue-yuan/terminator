from fastapi import Depends
from fastapi.requests import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from constants.error import ClientError
from controllers.models import WorkoutModel
from database import get_tx
from database.models.exercise import Exercise
from database.models.workout import Workout
from utils import AuthAPIRouter
from utils.exceptions import BadRequestException


router_with_auth = AuthAPIRouter(
    prefix="/exercise",
    tags=["Exercise"],
)


@router_with_auth.post("", response_model=WorkoutModel)
def create_exercise(request: Request, body: WorkoutModel, tx: sessionmaker = Depends(get_tx)):
    try:
        with tx.begin() as session:
            workout = Workout.create(
                session, request.state.user_id, body.datetime
            )

            session.flush()  # sync the object to database
            Exercise.bulk_create(session, body.exercises, workout)
    except IntegrityError as e:
        print(e)
        raise BadRequestException(
            error_code=ClientError.DATABASE_INTEGRITY_ERROR,
        )

    return body


@router_with_auth.delete("")
def delete_workout(request: Request, workout_id: str, tx: sessionmaker = Depends(get_tx)):
    try:
        with tx.begin() as session:
            user_id = request.state.user_id
            Workout.delete_by_workout_id(
                session, user_id, workout_id
            )
            return Workout.get_all(session, user_id)
    except IntegrityError as e:
        print(e)
        raise BadRequestException(
            error_code=ClientError.DATABASE_INTEGRITY_ERROR,
        )
