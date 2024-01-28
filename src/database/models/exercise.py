from sqlalchemy import INTEGER, VARCHAR, Column, ForeignKey, delete
from sqlalchemy.orm import SessionTransaction, relationship

from database.models.base import Base
from database.models.set import Set
from utils import generate_id


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(INTEGER, primary_key=True, index=True)
    exercise_id = Column(VARCHAR(50), nullable=False, unique=True)
    workout_id = Column(VARCHAR(50), ForeignKey(
        "workouts.workout_id", ondelete="CASCADE"
    ))
    exercise_type_id = Column(INTEGER, ForeignKey("exercise_types.id"))

    workout = relationship(
        "Workout", back_populates="exercises", passive_deletes=True
    )
    exercise_type = relationship(
        "ExerciseType", back_populates="exercises", passive_deletes=True
    )
    sets = relationship("Set", back_populates="exercise")

    @classmethod
    def get_by_exercise_id(cls, s: SessionTransaction, exercise_id: str):
        return s.query(cls).where(cls.exercise_id == exercise_id).one_or_none()

    @classmethod
    def create(cls, s: SessionTransaction, workout_id: str, exercise_type: int):
        exercise = cls(
            exercise_id=generate_id("exercise"),
            workout_id=workout_id,
            exercise_type_id=exercise_type,
        )

        s.add(exercise)
        return exercise

    @classmethod
    def bulk_create(cls, s: SessionTransaction, _exercises, workout):
        exercises = []
        sets = []

        for e in _exercises:
            exercise_id = generate_id("exercise")
            exercises.append(cls(
                exercise_id=exercise_id,
                workout_id=workout.workout_id,
                exercise_type_id=e.exercise_type_id,
            ))

            for ss in e.sets:
                sets.append(Set(
                    set_id=generate_id("set"),
                    exercise_id=exercise_id,
                    repetition=ss.repetition,
                    weight=ss.weight,
                ))

        s.bulk_save_objects(exercises)
        s.bulk_save_objects(sets)

        return exercises

    @classmethod
    def update(cls, s: SessionTransaction, exercise_id: str, exercise_type_id: str):
        return s.query(cls).filter_by(exercise_id=exercise_id).update({
            "exercise_type_id": exercise_type_id,
        })

    @classmethod
    def delete_by_exercise_id(cls, s: SessionTransaction, exercise_id: str):
        s.execute(delete(cls).where(
            (cls.exercise_id == exercise_id)
        ))

    @classmethod
    def delete_by_workout_id(cls, s: SessionTransaction, workout_id: str):
        s.execute(delete(cls).where(
            (cls.workout_id == workout_id)
        ))
