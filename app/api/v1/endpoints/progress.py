from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, ProgressSvc
from app.schemas.progress import ProgressOut, TitleIn, TitleOut
from app.services.errors import NotFound

router = APIRouter()


@router.get("", response_model=ProgressOut)
async def read_progress(
    user: CurrentUser,
    service: ProgressSvc,
    tz: str = Query("UTC", description="IANA time zone for weeks, days and times of day"),
    granted: bool = Query(False, description="Include titles given to you by hand (for apps that can show them)"),
) -> ProgressOut:
    """Your XP, level, title and achievements, from your whole history. Newly
    earned XP and tiers are banked as they're found; nothing earned is ever taken back."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown time zone: {tz}") from None
    return await service.progress(user, zone, granted=granted)


@router.put("/title", response_model=TitleOut | None)
async def put_title(data: TitleIn, user: CurrentUser, service: ProgressSvc) -> TitleOut | None:
    """Wear the title of an unlocked tier ("<achievement>:<target>"), or none (null)."""
    try:
        return await service.set_title(user, data.title)
    except NotFound:
        raise HTTPException(status_code=404, detail="That title isn't unlocked") from None


@router.put("/community-title", response_model=TitleOut | None)
async def put_community_title(data: TitleIn, user: CurrentUser, service: ProgressSvc) -> TitleOut | None:
    """Wear an unlocked community title next to your name, or none (null)."""
    try:
        return await service.set_title(user, data.title, community=True)
    except NotFound:
        raise HTTPException(status_code=404, detail="That community title isn't unlocked") from None
