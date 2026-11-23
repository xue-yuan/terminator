from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workout import utcnow


class CatalogExercise(Base):
    """An exercise in the built-in library everyone picks from (admins edit it).

    Picking one creates the user's own exercise (app/models/exercise.py) with
    the same name; the library only supplies suggestions, the Chinese name and
    the muscle group. Names are unique ignoring case.
    """

    __tablename__ = "catalog_exercises"
    __table_args__ = (
        CheckConstraint("log_type IN ('reps', 'time', 'cardio')", name="catalog_exercises_log_type_check"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    # Chinese name: searchable and shown under the English one.
    zh: Mapped[str | None] = mapped_column(String(100))
    # Other names people call it, space-separated: searchable, not shown.
    aka: Mapped[str | None] = mapped_column(String(300))
    muscle_group: Mapped[str] = mapped_column(String(20))
    # What a set of it is: weight × reps, a time, or a time and a distance (LogType).
    log_type: Mapped[str] = mapped_column(String(10), default="reps", server_default="reps")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )


Index("uq_catalog_exercises_name", func.lower(CatalogExercise.name), unique=True)
