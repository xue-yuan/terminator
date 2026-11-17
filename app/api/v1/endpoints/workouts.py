from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.api.deps import CurrentUser, WorkoutSvc
from app.models.workout import Workout
from app.schemas.workout import WorkoutActivity, WorkoutCreate, WorkoutIn, WorkoutOut
from app.services.errors import Invalid, NotFound

router = APIRouter()

NOT_FOUND = HTTPException(status_code=404, detail="Workout not found")


@router.get("/workouts/", response_model=list[WorkoutOut])
async def list_workouts(
    user: CurrentUser,
    service: WorkoutSvc,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """Most recent first."""
    return await service.list_for_user(user.id, skip=skip, limit=limit)


# Declared before /workouts/{workout_id}, which would otherwise take "activity" for an id.
@router.get("/workouts/activity", response_model=list[WorkoutActivity])
async def workout_activity(user: CurrentUser, service: WorkoutSvc) -> list[WorkoutActivity]:
    """All of your workouts in brief (date, name, length, working sets), most recent
    first. Small enough for the app to cache whole for its training calendar."""
    return await service.activity(user.id)


@router.post("/workouts/", response_model=WorkoutOut, status_code=status.HTTP_201_CREATED)
async def create_workout(data: WorkoutCreate, user: CurrentUser, service: WorkoutSvc) -> Workout:
    workout_id = data.id or uuid4()
    try:
        await service.get(user.id, workout_id)
    except NotFound:
        pass
    else:
        raise HTTPException(status_code=409, detail="Workout already exists; use PUT to update")
    workout, _ = await _upsert(service, user.id, workout_id, data)
    return workout


@router.get("/workouts/{workout_id}", response_model=WorkoutOut)
async def read_workout(workout_id: UUID, user: CurrentUser, service: WorkoutSvc) -> Workout:
    try:
        return await service.get(user.id, workout_id)
    except NotFound:
        raise NOT_FOUND from None


@router.put(
    "/workouts/{workout_id}",
    response_model=WorkoutOut,
    responses={201: {"description": "Created"}},
)
async def put_workout(
    workout_id: UUID, data: WorkoutIn, user: CurrentUser, service: WorkoutSvc, response: Response
) -> Workout:
    """Create or replace a workout by its client-generated id. Safe to retry."""
    workout, created = await _upsert(service, user.id, workout_id, data)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return workout


@router.delete("/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workout(workout_id: UUID, user: CurrentUser, service: WorkoutSvc) -> None:
    """Idempotent: deleting an already-deleted workout succeeds."""
    await service.delete(user.id, workout_id)


async def _upsert(
    service: WorkoutSvc, user_id: int, workout_id: UUID, data: WorkoutIn
) -> tuple[Workout, bool]:
    try:
        return await service.upsert(user_id, workout_id, data)
    except NotFound:
        raise NOT_FOUND from None
    except Invalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
