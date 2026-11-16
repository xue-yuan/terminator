from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser, CatalogSvc, CurrentUser
from app.schemas.catalog import CatalogIn, CatalogOut
from app.services.errors import Conflict, NotFound

router = APIRouter()

NOT_FOUND = HTTPException(status_code=404, detail="Not in the library")


@router.get("", response_model=list[CatalogOut])
async def read_catalog(_: CurrentUser, service: CatalogSvc) -> list[CatalogOut]:
    """The built-in exercise library, by name."""
    return await service.list()


@router.post("", response_model=CatalogOut, status_code=status.HTTP_201_CREATED)
async def add_to_catalog(data: CatalogIn, _: AdminUser, service: CatalogSvc) -> CatalogOut:
    """Add an exercise to the library. 409 when the name is taken (ignoring case)."""
    try:
        return await service.create(data)
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.put("/{entry_id}", response_model=CatalogOut)
async def update_catalog_entry(entry_id: int, data: CatalogIn, _: AdminUser, service: CatalogSvc) -> CatalogOut:
    """Change a library entry. Nobody's own exercises are renamed."""
    try:
        return await service.update(entry_id, data)
    except NotFound:
        raise NOT_FOUND from None
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalog_entry(entry_id: int, _: AdminUser, service: CatalogSvc) -> None:
    """Remove an exercise from the library (idempotent). Anyone who already uses it keeps theirs."""
    await service.delete(entry_id)
