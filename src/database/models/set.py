from sqlalchemy import INTEGER, NUMERIC, SMALLINT, VARCHAR, Column, ForeignKey
from sqlalchemy.orm import SessionTransaction, relationship

from database.models.base import Base


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
    def create(cls, s: SessionTransaction):
        ...
