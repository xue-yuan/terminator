"""Who may use the app.

ADMIN_EMAILS (environment) are the admins and are always allowed; admins let
others in from the app (the allowed_emails table). With no ADMIN_EMAILS set,
anyone who can sign in may use it (local development).
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.allowed_email import AllowedEmail
from app.models.user import User
from app.services.errors import Conflict


def normalize(email: str) -> str:
    return email.strip().lower()


class AccessService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def allowed(self, email: str) -> bool:
        if not settings.access_restricted or settings.is_admin(email):
            return True
        return await self.db.get(AllowedEmail, normalize(email)) is not None

    async def list(self) -> Sequence[tuple[AllowedEmail, User | None]]:
        """Allowed emails, newest first, with the account that uses each (if any)."""
        rows = await self.db.execute(
            select(AllowedEmail, User)
            # exact match (not LIKE: "_" in an email would be a wildcard)
            .outerjoin(User, func.lower(User.email) == AllowedEmail.email)
            .order_by(AllowedEmail.created_at.desc())
        )
        return rows.all()

    async def add(self, email: str, by: User) -> bool:
        """Let someone in. Returns whether they were new on the list."""
        email = normalize(email)
        if settings.is_admin(email):
            raise Conflict("That's an admin already (set in ADMIN_EMAILS)")
        if await self.db.get(AllowedEmail, email):
            return False
        self.db.add(AllowedEmail(email=email, added_by_id=by.id))
        await self.db.commit()
        return True

    async def remove(self, email: str) -> None:
        """Idempotent. They're signed out on their next request."""
        entry = await self.db.get(AllowedEmail, normalize(email))
        if entry:
            await self.db.delete(entry)
            await self.db.commit()
