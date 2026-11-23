from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import AwareDatetime

from app.api.deps import CommunitySvc, CurrentUser
from app.schemas.community import FeedItem, HighFiveIn, Player, TeamGoal
from app.services.errors import Invalid, NotFound

router = APIRouter()


@router.get("", response_model=list[Player])
async def list_players(user: CurrentUser, service: CommunitySvc) -> list[Player]:
    """Everyone who uses the app, with their level and the titles they wear, by name."""
    return await service.players(user)


@router.get("/goal", response_model=TeamGoal)
async def read_goal(user: CurrentUser, service: CommunitySvc) -> TeamGoal:
    """This week's goal for everyone together, and how far along it is."""
    return await service.goal(user)


@router.get("/feed", response_model=list[FeedItem])
async def read_feed(
    user: CurrentUser,
    service: CommunitySvc,
    before: AwareDatetime | None = Query(None, description="Older than this (the last item's `at`), for the next page"),
    since: AwareDatetime | None = Query(None, description="Finished at this time or later (the app asks from its own midnight)"),
    limit: int = Query(30, ge=1, le=100),
) -> list[FeedItem]:
    """Who finished a workout, and when, latest first. Nothing else about it is shared."""
    return await service.feed(user, before, limit, since)


async def _high_five(user, service, workout_id: UUID, on: bool) -> None:
    try:
        await service.high_five(user, workout_id, on)
    except NotFound:
        raise HTTPException(status_code=404, detail="Workout not found") from None
    except Invalid as err:
        raise HTTPException(status_code=400, detail=str(err)) from None


@router.put("/feed/{workout_id}/high-five", status_code=status.HTTP_204_NO_CONTENT)
async def put_high_five(workout_id: UUID, user: CurrentUser, service: CommunitySvc) -> None:
    """High-five someone's workout. Idempotent."""
    await _high_five(user, service, workout_id, True)


@router.delete("/feed/{workout_id}/high-five", status_code=status.HTTP_204_NO_CONTENT)
async def delete_high_five(workout_id: UUID, user: CurrentUser, service: CommunitySvc) -> None:
    """Take a high-five back. Idempotent."""
    await _high_five(user, service, workout_id, False)


@router.get("/high-fives", response_model=list[HighFiveIn])
async def read_high_fives(
    user: CurrentUser, service: CommunitySvc, since: AwareDatetime | None = Query(None)
) -> list[HighFiveIn]:
    """High-fives on your workouts (since a time), latest first."""
    return await service.high_fives_for(user, since)
