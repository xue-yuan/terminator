from httpx import delete
from sqlalchemy import INTEGER, TIMESTAMP, VARCHAR, Column, ForeignKey, delete
from sqlalchemy.orm import SessionTransaction, relationship
from sqlalchemy.sql import func

from controllers.models import QueryModel
from database import queries
from database.models.base import Base
from utils import generate_id


class Workout(Base):
    __tablename__ = "workouts"

    id = Column(INTEGER, primary_key=True, index=True)
    workout_id = Column(VARCHAR(50), nullable=False, unique=True)
    user_id = Column(VARCHAR(50), ForeignKey("users.user_id"))
    datetime = Column(
        TIMESTAMP(timezone=True),
        default=func.now(),
    )

    user = relationship("User", back_populates="workouts")
    exercises = relationship("Exercise", back_populates="workout")

    @classmethod
    def get_all(cls, s: SessionTransaction, user_id: str, query: QueryModel):
        result = [r for r in s.execute(
            queries.get_all_workouts(query.order.value),
            {
                "user_id": user_id,
                "start_date": "2020-01-01",
                "end_date": "2025-01-01",
                "limit": query.limit,
                "offset": query.offset,
            }
        )]

        return result[0][0]

    @classmethod
    def get_by_workout_id(cls, s: SessionTransaction, workout_id: str):
        return s.query(cls).where(cls.workout_id == workout_id).one_or_none()

    @classmethod
    def create(cls, s: SessionTransaction, user_id: str, datetime: str):
        workout = cls(
            workout_id=generate_id("workout"),
            user_id=user_id,
            datetime=datetime,
        )

        s.add(workout)
        return workout

    @classmethod
    def delete_by_workout_id(cls, s: SessionTransaction, user_id: str, workout_id: str):
        s.execute(delete(cls).where(
            (cls.user_id == user_id) &
            (cls.workout_id == workout_id)
        ))
