"""What a user has earned (app/services/progress.py). Earned is never taken
back: editing a workout down or deleting it leaves these rows as they are."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workout import utcnow


class XpAward(Base):
    """The XP a workout earned: its highest so far, so an edit can raise it but never lower it."""

    __tablename__ = "xp_awards"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # The workout's public id; no foreign key, the award outlives the workout.
    workout_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    xp: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AchievementUnlock(Base):
    """A tier of an achievement (and the title that comes with it), once reached.
    Tiers are named by their target, so reordering or adding tiers keeps them."""

    __tablename__ = "achievement_unlocks"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    achievement: Mapped[str] = mapped_column(String(40), primary_key=True)
    target: Mapped[float] = mapped_column(Float, primary_key=True)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The workout that reached it, when one did (not for weigh-ins or levels).
    workout_id: Mapped[UUID | None] = mapped_column(Uuid)
