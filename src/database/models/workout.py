from httpx import delete
from sqlalchemy import INTEGER, TIMESTAMP, VARCHAR, Column, ForeignKey, delete
from sqlalchemy.orm import SessionTransaction, relationship
from sqlalchemy.sql import func

from controllers.models import DateModel, QueryModel
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
    def get_by_workout_id(cls, s: SessionTransaction, workout_id: str):
        return s.query(cls).where(cls.workout_id == workout_id).one_or_none()

    @classmethod
    def get_by_auth_workout_id(cls, s: SessionTransaction, user_id: str, workout_id: str):
        return s.query(cls).where(
            (cls.user_id == user_id) &
            (cls.workout_id == workout_id)
        ).one_or_none()

    @classmethod
    def get_all(cls, s: SessionTransaction, user_id: str, query: QueryModel, date: DateModel):
        result = [r for r in s.execute(
            queries.get_all_workouts(query.order.value),
            {
                "user_id": user_id,
                "start_date": date.from_date,
                "end_date": date.to_date,
                "limit": query.limit,
                "offset": query.offset,
            }
        )]

        return result[0][0]

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
    def update_by_auth_workout_id(cls, s: SessionTransaction, user_id: str, workout_id: str, datetime):
        return s.query(cls).filter(
            (cls.user_id == user_id) &
            (cls.workout_id == workout_id)
        ).update({
            "datetime": datetime,
        })

    @classmethod
    def delete_by_workout_id(cls, s: SessionTransaction, workout_id: str):
        s.execute(delete(cls).where(
            (cls.workout_id == workout_id)
        ))

    @classmethod
    def delete_by_auth_workout_id(cls, s: SessionTransaction, user_id: str, workout_id: str):
        s.execute(delete(cls).where(
            (cls.user_id == user_id) &
            (cls.workout_id == workout_id)
        ))

    @classmethod
    def is_valid_user(cls, s: SessionTransaction, user_id: str, workout_id: str) -> bool:
        return bool(s.query(cls).where(
            (cls.user_id == user_id) &
            (cls.workout_id == workout_id)
        ).one_or_none())
