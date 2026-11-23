from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.progress import TitleOut


class Player(BaseModel):
    """Someone who uses the app, as everyone else sees them: no email, no numbers to compare beyond the level."""

    id: int
    name: str
    level: int
    title: TitleOut | None  # the title they wear
    community_title: TitleOut | None = None  # the community title they wear, next to the name
    you: bool


class TeamGoal(BaseModel):
    """This week's goal for everyone together: so many workouts between them."""

    week_start: date
    week_end: date  # the day after Sunday
    target: int
    total: int
    reached: bool
    trained: list[int]  # ids of the players who trained this week
    weeks_reached: int  # weeks the goal was reached that you trained in
    streak: int  # of those, in a row up to now


class FeedItem(BaseModel):
    """Someone finished a workout, and when: nothing more about it is shared."""

    workout_id: UUID
    player_id: int
    name: str
    at: datetime  # when it finished (its start when its length isn't known)
    you: bool  # your own
    high_fived: bool  # you high-fived it
    high_fivers: list[str]  # who high-fived it: only on your own workouts


class HighFiveIn(BaseModel):
    """Someone high-fived one of your workouts."""

    name: str
    workout_id: UUID
    workout_at: datetime
    at: datetime
