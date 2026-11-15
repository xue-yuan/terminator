from datetime import datetime

from pydantic import BaseModel, EmailStr


class AccessAdd(BaseModel):
    email: EmailStr


class AllowedEmailOut(BaseModel):
    email: str
    added_at: datetime
    signed_up: bool  # has signed in at least once


class AccessOut(BaseModel):
    restricted: bool  # false: no ADMIN_EMAILS, anyone may sign in
    admins: list[str]  # from ADMIN_EMAILS (read-only)
    allowed: list[AllowedEmailOut]
