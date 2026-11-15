from fastapi import APIRouter, HTTPException

from app.api.deps import BackupSvc, CurrentUser
from app.schemas.backup import BackupIn, BackupOut, ImportResult
from app.services.errors import Invalid

router = APIRouter()


@router.get("/export", response_model=BackupOut)
async def export_backup(user: CurrentUser, service: BackupSvc) -> BackupOut:
    """Everything of yours (exercises, workouts, plans, weigh-ins) as one JSON document."""
    return await service.export(user.id)


@router.post("/import", response_model=ImportResult)
async def import_backup(data: BackupIn, user: CurrentUser, service: BackupSvc) -> ImportResult:
    """Import a backup, or workouts converted from another app. Running the same
    import again updates instead of duplicating (plans with an existing name are skipped)."""
    try:
        return await service.import_backup(user.id, data)
    except Invalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
