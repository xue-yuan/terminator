from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.workout import utcnow


class SpotifyLink(Base):
    """A user's connection to Spotify (for playback controls while logging).

    Spotify's sign-in happens server side, because an installed iOS web app
    opens other sites in a separate browser whose storage it doesn't share.
    The refresh token never leaves the server; the app asks for short-lived
    access tokens. `pending_*` hold an unfinished sign-in (PKCE).
    """

    __tablename__ = "spotify_links"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pending_state: Mapped[str | None] = mapped_column(String(64), unique=True)
    pending_verifier: Mapped[str | None] = mapped_column(String(128))
    pending_redirect: Mapped[str | None] = mapped_column(String(300))
    pending_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
