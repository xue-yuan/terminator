from fastapi import APIRouter

from app.api.deps import DB, CurrentUser
from app.services.sync import SyncService

router = APIRouter()


@router.get("/state", response_model=dict[str, str])
async def sync_state(user: CurrentUser, db: DB) -> dict[str, str]:
    """A fingerprint per kind of data (workouts, exercises, plans,
    body_weights, summary, spotify, user). Refetch a kind only when its fingerprint changed."""
    return await SyncService(db).state(user)
