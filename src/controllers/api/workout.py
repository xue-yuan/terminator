from fastapi import Depends
from fastapi.requests import Request
from sqlalchemy.orm import sessionmaker

from controllers.models import DateModel, QueryModel, WorkoutModel
from database import get_tx
from database.models.exercise import Exercise
from database.models.workout import Workout
from utils import AuthAPIRouter

router_with_auth = AuthAPIRouter(
    prefix="/workout",
    tags=["Workout"],
)


def get_sort_validator():
    return QueryModel()


@router_with_auth.get("", response_model=WorkoutModel)
def get_workout(request: Request, workout_id: str, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        return Workout.get_by_auth_workout_id(
            s=session,
            user_id=request.state.user_id,
            workout_id=workout_id,
        )


@router_with_auth.get("s", )
def get_workouts(request: Request, query: QueryModel = Depends(), date: DateModel = Depends(), tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        return Workout.get_all(
            s=session,
            user_id=request.state.user_id,
            query=query,
        )


@router_with_auth.post("", response_model=WorkoutModel)
def create_workout(request: Request, body: WorkoutModel, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        workout = Workout.create(
            s=session,
            user_id=request.state.user_id,
            datetime=body.datetime,
        )

        session.flush()  # sync the object to database
        Exercise.bulk_create(
            s=session,
            _exercises=body.exercises,
            workout=workout,
        )

    return body


@router_with_auth.put("", response_model=WorkoutModel)
def update_workout(request: Request, workout_id: str, body: WorkoutModel, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        workout = Workout.update_by_auth_workout_id(
            s=session,
            user_id=request.state.user_id,
            workout_id=workout_id,
            datetime=body.datetime,
        )

        session.flush()
        Exercise.delete_by_workout_id(
            s=session,
            workout_id=workout_id,
        )
        Exercise.bulk_create(
            s=session,
            _exercises=body.exercises,
            workout=workout,
        )

    return body


@router_with_auth.delete("")
def delete_workout(request: Request, workout_id: str, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        Workout.delete_by_auth_workout_id(
            s=session,
            user_id=request.state.user_id,
            workout_id=workout_id,
        )

    return []
