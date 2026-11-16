"""The built-in exercise library: suggestions everyone sees when naming an
exercise, with a Chinese name, other names and a muscle group. Admins edit it.

Changing an entry never touches anyone's own exercises: those were copied
from it by name when picked, and belong to their owner from then on.
"""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import CatalogExercise
from app.models.workout import utcnow
from app.schemas.catalog import CatalogIn
from app.services.errors import Conflict, NotFound


class CatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self) -> Sequence[CatalogExercise]:
        return (await self.db.scalars(select(CatalogExercise).order_by(func.lower(CatalogExercise.name)))).all()

    async def _check_name(self, name: str, entry_id: int | None = None) -> None:
        stmt = select(CatalogExercise.name).where(func.lower(CatalogExercise.name) == name.lower())
        if entry_id is not None:
            stmt = stmt.where(CatalogExercise.id != entry_id)
        clash = await self.db.scalar(stmt)
        if clash is not None:
            raise Conflict(f'"{clash}" is already in the library')

    async def create(self, data: CatalogIn) -> CatalogExercise:
        await self._check_name(data.name)
        entry = CatalogExercise(**data.model_dump())
        self.db.add(entry)
        await self.db.commit()
        return entry

    async def update(self, entry_id: int, data: CatalogIn) -> CatalogExercise:
        entry = await self.db.get(CatalogExercise, entry_id)
        if entry is None:
            raise NotFound
        await self._check_name(data.name, entry_id)
        for key, value in data.model_dump().items():
            setattr(entry, key, value)
        entry.updated_at = utcnow()
        await self.db.commit()
        return entry

    async def delete(self, entry_id: int) -> None:
        """Idempotent."""
        entry = await self.db.get(CatalogExercise, entry_id)
        if entry is not None:
            await self.db.delete(entry)
            await self.db.commit()

    async def fingerprint(self) -> tuple:
        """Changes on every add, edit and delete (see app/services/sync.py)."""
        stmt = select(func.count(), func.max(CatalogExercise.updated_at))
        return tuple((await self.db.execute(stmt)).one())
