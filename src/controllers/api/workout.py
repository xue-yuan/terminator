from fastapi import Depends, Query
from fastapi.requests import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from constants.error import ClientError
from controllers.models import WorkoutModel, GetWorkoutModel, QueryModel
from database import get_tx
from database.models.exercise import Exercise
from database.models.workout import Workout
from utils import AuthAPIRouter
from utils.exceptions import BadRequestException


router_with_auth = AuthAPIRouter(
    prefix="/workout",
    tags=["Workout"],
)


def get_sort_validator():
    return QueryModel()


# TODO: limit offset sort order
@router_with_auth.get("s", )
def get_workouts(request: Request, query: QueryModel = Depends(), tx: sessionmaker = Depends(get_tx)):
    try:
        with tx.begin() as session:
            return Workout.get_all(session, request.state.user_id, query)
    except IntegrityError as e:
        raise BadRequestException(
            error_code=ClientError.DATABASE_INTEGRITY_ERROR,
        )


@router_with_auth.post("", response_model=WorkoutModel)
def create_workout(request: Request, body: WorkoutModel, tx: sessionmaker = Depends(get_tx)):
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


{
    "total": 2,
    "rows": [
        {
            "workout_id": "workout-1",
            "datetime": "2020-02-02T00:00:00+08:00",
            "exercises": [
                {
                    "exercise_type_id": 1,
                    "sets": [
                        {
                            "repetition": 1,
                            "weight": 50,
                        }
                    ]
                }
            ]
        },
        {

            "workout_id": "workout-2",
            "datetime": "2020-02-02T00:00:00+08:00",
            "exercises": [
                {
                    "exercise_type_id": 1,
                    "sets": [
                        {
                            "repetition": 1,
                            "weight": 50,
                        }
                    ]
                }
            ]
        }
    ]
}
