from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import AccessSvc, AdminUser
from app.core.config import settings
from app.schemas.access import AccessAdd, AccessOut, AllowedEmailOut
from app.services.errors import Conflict

router = APIRouter()


async def _overview(service: AccessSvc) -> AccessOut:
    return AccessOut(
        restricted=settings.access_restricted,
        admins=sorted(settings.admin_emails),
        allowed=[
            AllowedEmailOut(email=entry.email, added_at=entry.created_at, signed_up=user is not None)
            for entry, user in await service.list()
        ],
    )


@router.get("", response_model=AccessOut)
async def read_access(_: AdminUser, service: AccessSvc) -> AccessOut:
    """Admins (from ADMIN_EMAILS) and the emails they let in."""
    return await _overview(service)


@router.post("", response_model=AccessOut, responses={201: {"description": "Added"}})
async def allow_email(data: AccessAdd, admin: AdminUser, service: AccessSvc, response: Response) -> AccessOut:
    """Let someone use the app. Idempotent."""
    try:
        if await service.add(data.email, admin):
            response.status_code = status.HTTP_201_CREATED
    except Conflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return await _overview(service)


@router.delete("/{email}", response_model=AccessOut)
async def remove_email(email: str, _: AdminUser, service: AccessSvc) -> AccessOut:
    """Take someone off the list; they're signed out on their next request. Idempotent."""
    await service.remove(email)
    return await _overview(service)
