from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, RecapSvc
from app.schemas.recap import Period, RecapOut

router = APIRouter()


@router.get("", response_model=RecapOut)
async def read_recap(
    user: CurrentUser,
    service: RecapSvc,
    period: Period = Query("week"),
    day: date = Query(description="Any day of the week (Monday to Sunday) or month to review"),
    tz: str = Query("UTC", description="IANA time zone the days are in"),
) -> RecapOut:
    """A week's or month's training: totals against the period before, records,
    exercises and muscles worked, XP banked and titles reached."""
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown time zone: {tz}") from None
    return await service.recap(user.id, period, day, zone)
