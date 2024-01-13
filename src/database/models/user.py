from passlib.hash import bcrypt
from sqlalchemy import INTEGER, TIMESTAMP, VARCHAR
from sqlalchemy import Column
from sqlalchemy.orm import relationship, SessionTransaction
from sqlalchemy.sql import func

from database.models.base import Base
from utils import generate_id


class User(Base):
    __tablename__ = "users"

    id = Column(INTEGER, primary_key=True, index=True)
    user_id = Column(VARCHAR(50), nullable=False, unique=True)
    username = Column(VARCHAR(31), nullable=False, unique=True)
    password = Column(VARCHAR(60), nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True),
        default=func.now(),
    )

    workouts = relationship("Workout", back_populates="user")

    @classmethod
    def get_or_create(cls, s: SessionTransaction, username: str, password: str):
        user = cls.get_by_username(s, username)
        return user if user else cls.create(s, username, password)

    @classmethod
    def get_by_username(cls, s: SessionTransaction, username: str):
        return s.query(cls).where(cls.username == username).one_or_none()

    @classmethod
    def get_by_user_id(cls, s: SessionTransaction, user_id: str):
        return s.query(cls).where(cls.user_id == user_id).one_or_none()

    @classmethod
    def create(cls, s: SessionTransaction, username: str, password: str):
        user = cls(
            user_id=generate_id("user"),
            username=username,
            password=bcrypt.hash(
                secret=password,
            ),
        )

        s.add(user)
        return user

    def verify(self, password: str):
        return bcrypt.verify(password, self.password)
