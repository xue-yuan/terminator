from datetime import datetime

from pydantic import BaseModel, Field


class SpotifyConnect(BaseModel):
    # Where the app is open, e.g. "https://terminator.example" (the redirect
    # comes back there; it must be registered with the Spotify app).
    origin: str = Field(pattern=r"^https?://[^/\s]+$", max_length=200)


class SpotifyAuthorizeUrl(BaseModel):
    url: str


class SpotifyStatus(BaseModel):
    configured: bool
    connected: bool


class SpotifyToken(BaseModel):
    access_token: str
    expires_at: datetime
