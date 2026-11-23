"""Who else trains here (GET /community): everyone who may use the app, with
their level and the title they wear. Sorted by name, not by anything earned:
everyone trains for themselves here, nobody is ranked."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.allowed_email import AllowedEmail
from app.models.progress import AchievementUnlock
from app.models.user import User
from app.schemas.community import Player
from app.schemas.progress import TitleOut
from app.services.achievements import find_tier, level_for, title_key
from app.services.progress import xp_totals


class CommunityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _members(self) -> list[User]:
        users = (await self.db.execute(select(User).where(User.is_active))).scalars().all()
        if not settings.access_restricted:
            return list(users)
        allowed = set((await self.db.execute(select(AllowedEmail.email))).scalars())
        return [u for u in users if settings.is_admin(u.email) or u.email.strip().lower() in allowed]

    async def players(self, me: User) -> list[Player]:
        members = await self._members()
        if me.id not in {u.id for u in members}:
            members.append(me)
        ids = [u.id for u in members]
        xp = await xp_totals(self.db, ids)
        unlocked = set(
            (
                await self.db.execute(
                    select(AchievementUnlock.user_id, AchievementUnlock.achievement, AchievementUnlock.target).where(
                        AchievementUnlock.user_id.in_([u.id for u in members if u.title])
                    )
                )
            ).all()
        )
        players = []
        for u in members:
            found = find_tier(u.title) if u.title else None
            title = None
            if found and (u.id, found[0].id, found[1].target) in unlocked:
                title = TitleOut(key=title_key(*found), title=found[1].title, medal=found[1].medal)
            players.append(
                Player(
                    id=u.id,
                    name=(u.full_name or "").strip() or "Player",
                    level=level_for(xp[u.id]),
                    title=title,
                    you=u.id == me.id,
                )
            )
        return sorted(players, key=lambda p: (p.name.casefold(), p.id))
