from html import escape

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import HTMLResponse

from app.api.deps import CurrentUser, SpotifySvc
from app.core.config import settings
from app.schemas.spotify import SpotifyAuthorizeUrl, SpotifyConnect, SpotifyStatus, SpotifyToken
from app.services.spotify import NotConnected, SpotifyError

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


def _page(title: str, body: str, ok: bool) -> HTMLResponse:
    color = "#1d8a4c" if ok else "#cc2b1d"
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{escape(title)}</title>
<style>body{{font:18px/1.5 system-ui,sans-serif;background:#f2f0ea;color:#141414;margin:0;padding:48px 24px}}
h1{{font-size:28px;margin:0 0 8px;border-left:6px solid {color};padding-left:12px}}a{{color:#141414}}</style>
</head><body><h1>{escape(title)}</h1><p>{escape(body)}</p><p><a href="/">Open Terminator</a></p></body></html>""",
        status_code=200 if ok else 400,
    )


@router.get("/callback", include_in_schema=False)
async def spotify_callback(
    service: SpotifySvc,
    state: str = Query(""),
    code: str = Query(""),
    error: str = Query(""),
) -> HTMLResponse:
    """Where Spotify sends the browser back after signing in."""
    if error or not code:
        return _page("Spotify not connected", "Spotify didn't allow access. Try again from the app.", ok=False)
    try:
        await service.finish(state, code)
    except SpotifyError as exc:
        return _page("Spotify not connected", str(exc), ok=False)
    return _page("Spotify connected", "Go back to Terminator: the music controls are ready.", ok=True)


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
