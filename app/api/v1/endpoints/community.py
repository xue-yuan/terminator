from fastapi import APIRouter

from app.api.deps import CommunitySvc, CurrentUser
from app.schemas.community import Player

router = APIRouter()


@router.get("", response_model=list[Player])
async def list_players(user: CurrentUser, service: CommunitySvc) -> list[Player]:
    """Everyone who uses the app, with their level and the title they wear, by name."""
    return await service.players(user)
