from sqlalchemy import INTEGER, VARCHAR, Column, delete
from sqlalchemy.orm import SessionTransaction, relationship

from database.models.base import Base


class ExerciseType(Base):
    __tablename__ = "exercise_types"

    id = Column(INTEGER, primary_key=True, index=True)
    exercise_name = Column(VARCHAR(255), nullable=False, unique=True)

    exercises = relationship("Exercise", back_populates="exercise_type")

    @classmethod
    def get_by_id(cls, s: SessionTransaction, id: int):
        return s.query(cls).where(cls.id == id).one_or_none()

    @classmethod
    def get_all(cls, s: SessionTransaction):
        return [{
            "exercise_type_id": e.id,
            "exercise_name": e.exercise_name,
        } for e in s.query(cls).order_by(cls.exercise_name.asc()).all()]

    @classmethod
    def create(cls, s: SessionTransaction, exercise_name: str):
        exercise = cls(
            exercise_name=exercise_name,
        )

        s.add(exercise)
        return exercise

    @classmethod
    def update(cls, s: SessionTransaction, id: int, exercise_name: str):
        return s.query(cls).filter_by(id=id).update({
            "exercise_name": exercise_name,
        })

    @classmethod
    def delete_by_id(cls, s: SessionTransaction, id: int):
        s.execute(delete(cls).where((cls.id == id)))
