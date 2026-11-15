from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import RedirectResponse

from app.api.deps import CurrentUser, SpotifySvc
from app.core.config import settings
from app.schemas.spotify import SpotifyAuthorizeUrl, SpotifyConnect, SpotifyStatus, SpotifyToken
from app.services.spotify import NotConnected, SpotifyError, SpotifyExpired

router = APIRouter()


def _require_configured() -> None:
    if not settings.SPOTIFY_CLIENT_ID:
        raise HTTPException(status_code=404, detail="Spotify isn't set up on this server")


@router.get("/status", response_model=SpotifyStatus)
async def spotify_status(user: CurrentUser, service: SpotifySvc) -> SpotifyStatus:
    return SpotifyStatus(
        configured=bool(settings.SPOTIFY_CLIENT_ID),
        connected=bool(settings.SPOTIFY_CLIENT_ID) and await service.connected(user.id),
    )


@router.post("/connect", response_model=SpotifyAuthorizeUrl)
async def spotify_connect(data: SpotifyConnect, user: CurrentUser, service: SpotifySvc) -> SpotifyAuthorizeUrl:
    """Start signing in to Spotify: open the returned URL."""
    _require_configured()
    return SpotifyAuthorizeUrl(url=await service.start(user.id, data.origin))


# Back into the app, which shows the result in its own design. Relative, so the
# browser resolves it against the address the app is open at.
DONE = "/spotify/done"


@router.get("/callback", include_in_schema=False)
async def spotify_callback(
    service: SpotifySvc,
    state: str = Query(""),
    code: str = Query(""),
    error: str = Query(""),
) -> RedirectResponse:
    """Where Spotify sends the browser back after signing in."""
    if error or not code:
        return RedirectResponse(f"{DONE}?{urlencode({'error': 'denied'})}", status_code=303)
    try:
        await service.finish(state, code)
    except SpotifyExpired:
        return RedirectResponse(f"{DONE}?{urlencode({'error': 'expired'})}", status_code=303)
    except SpotifyError:
        return RedirectResponse(f"{DONE}?{urlencode({'error': 'failed'})}", status_code=303)
    return RedirectResponse(f"{DONE}?connected=1", status_code=303)


@router.post("/token", response_model=SpotifyToken)
async def spotify_token(user: CurrentUser, service: SpotifySvc) -> SpotifyToken:
    """A short-lived access token for Spotify's Web API (409 when not connected)."""
    _require_configured()
    try:
        token, expires_at = await service.access_token(user.id)
    except NotConnected:
        raise HTTPException(status_code=409, detail="Spotify isn't connected") from None
    except SpotifyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return SpotifyToken(access_token=token, expires_at=expires_at)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def spotify_disconnect(user: CurrentUser, service: SpotifySvc) -> None:
    await service.disconnect(user.id)
