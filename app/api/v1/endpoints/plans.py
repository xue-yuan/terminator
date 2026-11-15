from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, PlanSvc
from app.models.plan import Plan
from app.models.user import User
from app.schemas.plan import PlanIn, PlanOut
from app.services.errors import NotFound

router = APIRouter()

NOT_FOUND = HTTPException(status_code=404, detail="Plan not found")


def _out(plan: Plan, user: User) -> PlanOut:
    return PlanOut.model_validate(plan).model_copy(
        update={"is_active": plan.id == user.active_plan_id}
    )


@router.get("/", response_model=list[PlanOut])
async def list_plans(user: CurrentUser, service: PlanSvc) -> list[PlanOut]:
    """Plans you created, newest first."""
    return [_out(p, user) for p in await service.list_own(user.id)]


@router.post("/", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(data: PlanIn, user: CurrentUser, service: PlanSvc) -> PlanOut:
    return _out(await service.create(user.id, data), user)


@router.post("/deactivate", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_plan(user: CurrentUser, service: PlanSvc) -> None:
    await service.set_active(user, None)


@router.get("/{plan_id}", response_model=PlanOut)
async def read_plan(plan_id: int, user: CurrentUser, service: PlanSvc) -> PlanOut:
    try:
        return _out(await service.get_visible(user.id, plan_id), user)
    except NotFound:
        raise NOT_FOUND from None


@router.put("/{plan_id}", response_model=PlanOut)
async def update_plan(plan_id: int, data: PlanIn, user: CurrentUser, service: PlanSvc) -> PlanOut:
    try:
        return _out(await service.update(user.id, plan_id, data), user)
    except NotFound:
        raise NOT_FOUND from None


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: int, user: CurrentUser, service: PlanSvc) -> None:
    try:
        await service.delete(user.id, plan_id)
    except NotFound:
        raise NOT_FOUND from None


@router.post("/{plan_id}/activate", response_model=PlanOut)
async def activate_plan(plan_id: int, user: CurrentUser, service: PlanSvc) -> PlanOut:
    """Make this the plan you're following (replaces any previous one)."""
    try:
        await service.set_active(user, plan_id)
        return _out(await service.get_visible(user.id, plan_id), user)
    except NotFound:
        raise NOT_FOUND from None
