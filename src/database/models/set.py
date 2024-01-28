from sqlalchemy import (
    INTEGER, NUMERIC, SMALLINT, VARCHAR,
    Column, ForeignKey, delete
)
from sqlalchemy.orm import SessionTransaction, relationship

from database.models.base import Base
from utils import generate_id


class Set(Base):
    __tablename__ = "sets"

    id = Column(INTEGER, primary_key=True, index=True)
    set_id = Column(VARCHAR(50), nullable=False, unique=True)
    exercise_id = Column(VARCHAR(50), ForeignKey(
        "exercises.exercise_id", ondelete="CASCADE"
    ))
    repetition = Column(SMALLINT, nullable=True)
    weight = Column(NUMERIC(5, 2), nullable=True)  # kg

    exercise = relationship(
        "Exercise", back_populates="sets", passive_deletes=True
    )

    @classmethod
    def get_by_exercise_id(cls, s: SessionTransaction, set_id: str):
        return s.query(cls).where(cls.set_id == set_id).one_or_none()

    @classmethod
    def bulk_create(cls, s: SessionTransaction, _sets, exercise):
        sets = []

        for ss in _sets:
            sets.append(
                Set(
                    set_id=generate_id("set"),
                    exercise_id=exercise.exercise_id,
                    repetition=ss.repetition,
                    weight=ss.weight,
                )
            )

        s.bulk_save_objects(sets)

        return sets

    @classmethod
    def delete_by_exercise_id(cls, s: SessionTransaction, exercise_id: str):
        s.execute(delete(cls).where(
            (cls.exercise_id == exercise_id)
        ))
