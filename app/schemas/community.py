from pydantic import BaseModel

from app.schemas.progress import TitleOut


class Player(BaseModel):
    """Someone who uses the app, as everyone else sees them: no email, no numbers to compare beyond the level."""

    id: int
    name: str
    level: int
    title: TitleOut | None  # the title they wear
    you: bool
