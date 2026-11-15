"""Spotify sign-in (Authorization Code with PKCE, done by the server) and
short-lived access tokens for the app, which then talks to Spotify's Web API
directly to control playback."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.spotify import SpotifyLink
from app.models.workout import utcnow

SCOPES = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
PENDING_FOR = timedelta(minutes=10)
CALLBACK_PATH = "/api/v1/spotify/callback"


class SpotifyError(Exception):
    """Spotify refused or couldn't be reached."""


class NotConnected(Exception):
    pass


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class SpotifyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _link(self, user_id: int) -> SpotifyLink | None:
        return await self.db.get(SpotifyLink, user_id)

    async def _token_request(self, data: dict[str, str]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    f"{settings.SPOTIFY_ACCOUNTS_URL}/api/token",
                    data={"client_id": settings.SPOTIFY_CLIENT_ID, **data},
                )
        except httpx.HTTPError as exc:
            raise SpotifyError("Couldn't reach Spotify") from exc
        if response.status_code != 200:
            raise SpotifyError(f"Spotify refused ({response.status_code})")
        return response.json()

    def _store(self, link: SpotifyLink, tokens: dict[str, Any]) -> None:
        link.access_token = tokens["access_token"]
        # Spotify may or may not send a new refresh token; keep the old one if not.
        link.refresh_token = tokens.get("refresh_token") or link.refresh_token
        link.expires_at = datetime.now(UTC) + timedelta(seconds=int(tokens.get("expires_in", 3600)))
        link.updated_at = utcnow()

    async def start(self, user_id: int, app_origin: str) -> str:
        """Begin signing in; returns Spotify's authorization URL. The redirect
        comes back to this API under the origin the app is served from (which
        must be registered with the Spotify app)."""
        link = await self._link(user_id) or SpotifyLink(user_id=user_id)
        self.db.add(link)
        verifier = secrets.token_urlsafe(64)[:96]
        link.pending_state = secrets.token_urlsafe(24)
        link.pending_verifier = verifier
        link.pending_redirect = f"{app_origin.rstrip('/')}{CALLBACK_PATH}"
        link.pending_at = datetime.now(UTC)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.SPOTIFY_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": link.pending_redirect,
                "code_challenge_method": "S256",
                "code_challenge": _challenge(verifier),
                "state": link.pending_state,
                "scope": SCOPES,
            }
        )
        return f"{settings.SPOTIFY_ACCOUNTS_URL}/authorize?{query}"

    async def finish(self, state: str, code: str) -> None:
        """Spotify's redirect: trade the code for tokens."""
        link = (
            await self.db.execute(select(SpotifyLink).where(SpotifyLink.pending_state == state))
        ).scalar_one_or_none()
        if link is None or link.pending_at is None or datetime.now(UTC) - link.pending_at > PENDING_FOR:
            raise SpotifyError("This sign-in expired. Start again from the app.")
        tokens = await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": link.pending_redirect,
                "code_verifier": link.pending_verifier,
            }
        )
        self._store(link, tokens)
        link.pending_state = link.pending_verifier = link.pending_redirect = None
        link.pending_at = None
        await self.db.commit()

    async def connected(self, user_id: int) -> bool:
        link = await self._link(user_id)
        return bool(link and link.refresh_token)

    async def access_token(self, user_id: int) -> tuple[str, datetime]:
        """A valid access token (refreshed when it's about to expire)."""
        link = await self._link(user_id)
        if not link or not link.refresh_token:
            raise NotConnected
        if not link.access_token or link.expires_at is None or link.expires_at - datetime.now(UTC) < timedelta(seconds=60):
            try:
                tokens = await self._token_request({"grant_type": "refresh_token", "refresh_token": link.refresh_token})
            except SpotifyError:
                # Revoked or expired (refresh tokens last six months): sign in again.
                link.access_token = link.refresh_token = link.expires_at = None
                await self.db.commit()
                raise NotConnected from None
            self._store(link, tokens)
            await self.db.commit()
        return link.access_token, link.expires_at

    async def disconnect(self, user_id: int) -> None:
        link = await self._link(user_id)
        if link:
            await self.db.delete(link)
            await self.db.commit()
