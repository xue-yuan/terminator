from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.security.utils import get_authorization_scheme_param
from psycopg2.errorcodes import UNIQUE_VIOLATION
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import config
from constants.error import ClientError
from constants.example import EMPTY_EXAMPLE_RESPONSES
from controllers.models import AuthModel, TokenModel
from database import get_tx
from database.models.user import User
from database.redis import Redis
from utils import AuthAPIRouter, token
from utils.exceptions import BadRequestException
from utils.responses import EmptyResponse

router = APIRouter(tags=["Auth"])
router_with_auth = AuthAPIRouter(tags=["Auth"])


@router.post("/login", response_model=TokenModel)
def login(body: AuthModel, tx: sessionmaker = Depends(get_tx)):
    with tx.begin() as session:
        user = User.get_by_username(session, body.username)

    if not user:
        raise BadRequestException(
            error_code=ClientError.INCORRECT_USERNAME_OR_PASSWORD
        )

    ok = user.verify(body.password)
    if not ok:
        raise BadRequestException(
            error_code=ClientError.INCORRECT_USERNAME_OR_PASSWORD
        )

    return TokenModel(
        token=token.generate(user_id=user.user_id)
    )


@router.post("/register", response_model=TokenModel)
def register(body: AuthModel, tx: sessionmaker = Depends(get_tx)):
    try:
        with tx.begin() as session:
            user = User.create(session, body.username, body.password)
    except IntegrityError as e:
        if e.orig.pgcode == UNIQUE_VIOLATION:
            raise BadRequestException(
                error_code=ClientError.DUPLICATE_USERNAME,
            )

        raise BadRequestException(
            error_code=ClientError.DATABASE_INTEGRITY_ERROR,
        )

    return TokenModel(
        token=token.generate(user_id=user.user_id)
    )


@router_with_auth.post("/logout", responses=EMPTY_EXAMPLE_RESPONSES)
def logout(request: Request):
    _, credentials = get_authorization_scheme_param(
        request.headers.get("authorization")
    )
    Redis().set(credentials, request.state.user_id, config.TOKEN_TTL*60*60)

    return EmptyResponse()


@router_with_auth.post("/refresh_token", response_model=TokenModel)
def refresh_token(request: Request):
    _, credentials = get_authorization_scheme_param(
        request.headers.get("authorization")
    )
    Redis().set(credentials, request.state.user_id, config.OLD_TOKEN_TTL*60*60)

    return TokenModel(
        token=token.generate(user_id=request.state.user_id)
    )
