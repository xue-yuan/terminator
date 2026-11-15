from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.services.access import AccessService

GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
DEV_USER_EMAIL = "dev@terminator.fit"


class GoogleAuthError(Exception):
    """The ID token is invalid or not acceptable."""


class GoogleUnavailable(Exception):
    """Google's token endpoint couldn't be reached (network error or 5xx)."""


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _tokeninfo(self, id_token: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(GOOGLE_TOKEN_INFO_URL, params={"id_token": id_token})
        except httpx.HTTPError as exc:
            raise GoogleUnavailable from exc
        if response.status_code >= 500:
            raise GoogleUnavailable
        return response.json() if response.status_code == 200 else None

    async def verify_google_token(self, id_token: str) -> dict[str, Any]:
        """Validate a Google Identity Services ID token (signature checked by Google)."""
        data = await self._tokeninfo(id_token)
        if not data:
            raise GoogleAuthError("Invalid Google token")
        if data.get("aud") != settings.GOOGLE_CLIENT_ID:
            raise GoogleAuthError("Token was issued for a different client")
        if data.get("iss") not in GOOGLE_ISSUERS:
            raise GoogleAuthError("Unexpected token issuer")
        if str(data.get("email_verified")).lower() != "true" or not data.get("email"):
            raise GoogleAuthError("Google account email is not verified")
        return data

    async def get_or_create_google_user(self, google_data: dict[str, Any]) -> User:
        sub, email = google_data["sub"], google_data["email"]
        user = (await self.db.execute(select(User).where(User.google_sub == sub))).scalar_one_or_none()
        if user is None:
            user = (await self.db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if user is None:
                user = User(email=email, full_name=google_data.get("name"))
                self.db.add(user)
            user.google_sub = sub
            if not user.full_name:
                user.full_name = google_data.get("name")
            await self.db.commit()
        return user

    async def get_or_create_dev_user(self) -> User:
        user = (await self.db.execute(select(User).where(User.email == DEV_USER_EMAIL))).scalar_one_or_none()
        if user is None:
            user = User(email=DEV_USER_EMAIL, full_name="John Connor")
            self.db.add(user)
            await self.db.commit()
        return user

    async def get_active_user(self, user_id: int) -> User | None:
        """The user, unless deactivated or no longer allowed (app/services/access.py).
        Every authenticated request and token refresh goes through here."""
        user = await self.db.get(User, user_id)
        if user and user.is_active and await AccessService(self.db).allowed(user.email):
            return user
        return None
