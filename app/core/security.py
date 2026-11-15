from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]


class InvalidToken(Exception):
    pass


def _create_token(user_id: int, token_type: TokenType, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + lifetime}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(
        user_id, "access", timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )


def create_refresh_token(user_id: int) -> str:
    return _create_token(
        user_id, "refresh", timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )


def decode_token(token: str, expected_type: TokenType) -> int:
    """Return the user id in a valid token of the expected type, else raise InvalidToken."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidToken from exc
    if payload.get("type") != expected_type:
        raise InvalidToken
    try:
        return int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise InvalidToken from exc
