from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.exercise import Exercise


class Plan(Base):
    """A reusable programme, e.g. 'Upper / Lower 4x'."""

    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    creator_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    days: Mapped[list["PlanDay"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanDay.order",
        passive_deletes=True,
    )


class PlanDay(Base):
    """One training day in a plan, e.g. 'Lower A'."""

    __tablename__ = "plan_days"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    order: Mapped[int] = mapped_column(default=0, server_default="0")

    plan: Mapped[Plan] = relationship(back_populates="days")
    exercises: Mapped[list["PlanExercise"]] = relationship(
        back_populates="day",
        cascade="all, delete-orphan",
        order_by="PlanExercise.order",
        passive_deletes=True,
    )


class PlanExercise(Base):
    __tablename__ = "plan_exercises"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("plan_days.id", ondelete="CASCADE"))
    exercise_id: Mapped[UUID] = mapped_column(ForeignKey("exercises.id"))
    target_sets: Mapped[int | None]
    target_reps_min: Mapped[int | None]
    target_reps_max: Mapped[int | None]
    # Consecutive exercises with the same number are a superset.
    superset: Mapped[int | None]
    order: Mapped[int] = mapped_column(default=0, server_default="0")

    day: Mapped[PlanDay] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship(lazy="joined", innerjoin=True)

    @property
    def exercise_name(self) -> str:
        return self.exercise.name


Index("ix_plan_exercises_exercise_id", PlanExercise.exercise_id)
