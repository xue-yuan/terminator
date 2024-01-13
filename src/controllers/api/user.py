from fastapi import APIRouter, Depends
from fastapi.requests import Request
from sqlalchemy.orm import sessionmaker

from controllers.models import UserModel
from database import get_tx
from database.models.user import User
from utils import AuthAPIRouter

router = APIRouter(
    prefix="/user",
    tags=["User"],
)
router_with_auth = AuthAPIRouter(
    prefix="/user",
    tags=["User"],
)


@router.get("/no_auth")
def get_user():
    return {"foo": "bar2"}


@router_with_auth.get("", response_model=UserModel)
def get_user(request: Request, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        user = User.get_by_user_id(session, request.state.user_id)

    return UserModel(
        user_id=user.user_id,
        username=user.username,
    )
