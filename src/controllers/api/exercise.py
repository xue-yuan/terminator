from fastapi import Depends
from fastapi.requests import Request
from sqlalchemy.orm import sessionmaker

from constants.error import ClientError
from controllers.models import ExerciseModel, WorkoutModel
from database import get_tx
from database.models.exercise import Exercise
from database.models.set import Set
from database.models.workout import Workout
from utils import AuthAPIRouter
from utils.exceptions import ForbiddenException

router_with_auth = AuthAPIRouter(
    prefix="/exercise",
    tags=["Exercise"],
)


@router_with_auth.post("", response_model=WorkoutModel)
def create_exercise(request: Request, workout_id: str, body: ExerciseModel, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        if not Workout.is_valid_user(
            s=session,
            user_id=request.state.user_id,
            workout_id=workout_id,
        ):
            raise ForbiddenException(
                error_code=ClientError.INVALID_USER_OPERATION,
            )

        exercise = Exercise.create(
            s=session,
            workout_id=workout_id,
            exercise_type=body.exercise_type,
        )

        session.flush()
        Set.bulk_create(
            s=session,
            sets=body.sets,
            exercise=exercise
        )

    return Workout.get_by_workout_id(workout_id)


@router_with_auth.put("", response_model=WorkoutModel)
def update_exercise(request: Request, workout_id: str, exercise_id: str, body: ExerciseModel, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        if not Workout.is_valid_user(
            s=session,
            user_id=request.state.user_id,
            workout_id=workout_id,
        ):
            raise ForbiddenException(
                error_code=ClientError.INVALID_USER_OPERATION,
            )

        exercise = Exercise.update(
            s=session,
            exercise_id=exercise_id,
            exercise_type_id=body.exercise_type_id,

        )

        session.flush()
        Set.delete_by_exercise_id(
            s=session,
            exercise_id=exercise_id
        )
        Set.bulk_create(
            s=session,
            sets=body.sets,
            exercise=exercise,
        )

    return Workout.get_by_workout_id(workout_id)


@router_with_auth.delete("", response_model=WorkoutModel)
def delete_exercise(request: Request, workout_id: str, exercise_id: str, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        if not Workout.is_valid_user(
            s=session,
            user_id=request.state.user_id,
            workout_id=workout_id,
        ):
            raise ForbiddenException(
                error_code=ClientError.INVALID_USER_OPERATION,
            )

        Exercise.delete_by_exercise_id(
            s=session,
            exercise_id=exercise_id,
        )

    return Workout.get_by_workout_id(workout_id)
