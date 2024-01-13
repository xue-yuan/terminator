from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

import config
from database.models.base import Base
from database.models.exercise_type import ExerciseType
from database.models.exercise import Exercise
from database.models.set import Set
from database.models.workout import Workout


url = URL.create(
    drivername=config.DATABASE["drivername"],
    database=config.DATABASE["database"],
    username=config.DATABASE["username"],
    password=config.DATABASE["password"],
    host=config.DATABASE["host"],
    port=config.DATABASE["port"],
)


engine = create_engine(
    url,
    echo=True,
    max_overflow=config.DATABASE["max_overflow"],
    pool_recycle=config.DATABASE["pool_recycle"],
    pool_size=config.DATABASE["pool_size"],
    pool_timeout=config.DATABASE["pool_timeout"],
)

Session = sessionmaker(bind=engine, expire_on_commit=False)


def get_tx():
    return Session


def initialize():
    Base.metadata.create_all(bind=engine)
