from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import AuthSvc, CurrentUser, SummarySvc, unauthorized
from app.core import security
from app.core.config import settings
from app.models.user import User
from app.schemas.token import AuthConfig, GoogleLoginRequest, RefreshRequest, Token
from app.schemas.user import Summary, UserOut
from app.services.auth import GoogleAuthError, GoogleUnavailable

router = APIRouter()


def _issue_tokens(user: User) -> Token:
    return Token(
        access_token=security.create_access_token(user.id),
        refresh_token=security.create_refresh_token(user.id),
    )


@router.get("/auth/config", response_model=AuthConfig)
async def auth_config() -> AuthConfig:
    """Which sign-in methods (and integrations) the frontend should offer."""
    return AuthConfig(
        google_client_id=settings.GOOGLE_CLIENT_ID if settings.google_login_enabled else None,
        dev_login_enabled=settings.dev_login_enabled,
        spotify_client_id=settings.SPOTIFY_CLIENT_ID or None,
    )


@router.post("/auth/google", response_model=Token)
async def login_google(payload: GoogleLoginRequest, auth: AuthSvc) -> Token:
    """Exchange a Google Identity Services ID token for API tokens."""
    if not settings.google_login_enabled:
        raise HTTPException(status_code=404, detail="Google sign-in is not configured")
    try:
        google_data = await auth.verify_google_token(payload.id_token)
    except GoogleAuthError as exc:
        raise unauthorized(str(exc)) from None
    except GoogleUnavailable:
        raise HTTPException(
            status_code=503, detail="Couldn't reach Google to check the sign-in. Try again."
        ) from None
    user = await auth.get_or_create_google_user(google_data)
    if not user.is_active:
        raise unauthorized("User is inactive")
    return _issue_tokens(user)


@router.post("/auth/login/dev", response_model=Token)
async def login_dev(auth: AuthSvc) -> Token:
    """Local development only: sign in as the dev user without credentials."""
    if not settings.dev_login_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return _issue_tokens(await auth.get_or_create_dev_user())


@router.post("/auth/refresh", response_model=Token)
async def refresh(payload: RefreshRequest, auth: AuthSvc) -> Token:
    """Trade a refresh token for a fresh access + refresh token pair."""
    try:
        user_id = security.decode_token(payload.refresh_token, "refresh")
    except security.InvalidToken:
        raise unauthorized("Invalid or expired refresh token") from None
    user = await auth.get_active_user(user_id)
    if user is None:
        raise unauthorized("User not found or inactive")
    return _issue_tokens(user)


@router.get("/users/me", response_model=UserOut)
async def read_me(user: CurrentUser) -> User:
    return user


@router.get("/users/me/summary", response_model=Summary)
async def read_summary(
    user: CurrentUser,
    summary: SummarySvc,
    tz: str = Query("UTC", description="IANA time zone used for week boundaries"),
) -> Summary:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail=f"Unknown time zone: {tz}") from None
    return await summary.summary(user, zone)
