from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import BodyWeightSvc, CurrentUser
from app.models.body_weight import BodyWeight
from app.schemas.body_weight import BodyWeightIn, BodyWeightOut
from app.services.errors import NotFound

router = APIRouter()


@router.get("/", response_model=list[BodyWeightOut])
async def list_body_weights(user: CurrentUser, service: BodyWeightSvc):
    """Your weigh-ins, newest first."""
    return await service.list(user.id)


@router.put("/{entry_id}", response_model=BodyWeightOut, responses={201: {"description": "Created"}})
async def put_body_weight(
    entry_id: UUID, data: BodyWeightIn, user: CurrentUser, service: BodyWeightSvc, response: Response
) -> BodyWeight:
    """Create or replace a weigh-in by its client-generated id. Safe to retry."""
    try:
        entry, created = await service.upsert(user.id, entry_id, data)
    except NotFound:
        raise HTTPException(status_code=404, detail="Weigh-in not found") from None
    if created:
        response.status_code = status.HTTP_201_CREATED
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_body_weight(entry_id: UUID, user: CurrentUser, service: BodyWeightSvc) -> None:
    """Idempotent."""
    await service.delete(user.id, entry_id)
