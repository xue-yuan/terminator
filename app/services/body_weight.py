from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_weight import BodyWeight
from app.models.workout import utcnow
from app.schemas.body_weight import BodyWeightIn
from app.services.errors import NotFound


class BodyWeightService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, user_id: int, limit: int | None = 2000) -> Sequence[BodyWeight]:
        """Newest first (all of them with `limit=None`)."""
        stmt = (
            select(BodyWeight)
            .where(BodyWeight.user_id == user_id)
            .order_by(BodyWeight.measured_at.desc())
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def upsert(self, user_id: int, entry_id: UUID, data: BodyWeightIn) -> tuple[BodyWeight, bool]:
        """Create or replace a weigh-in. Returns (entry, created)."""
        entry = await self.db.get(BodyWeight, entry_id)
        if entry is not None and entry.user_id != user_id:
            raise NotFound
        created = entry is None
        if created:
            entry = BodyWeight(id=entry_id, user_id=user_id)
            self.db.add(entry)
        for key, value in data.model_dump().items():
            setattr(entry, key, value)
        entry.updated_at = utcnow()
        await self.db.commit()
        return entry, created

    async def delete(self, user_id: int, entry_id: UUID) -> None:
        """Idempotent: deleting a missing entry is not an error."""
        entry = await self.db.get(BodyWeight, entry_id)
        if entry is not None and entry.user_id == user_id:
            await self.db.delete(entry)
            await self.db.commit()
