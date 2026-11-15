import os
from pathlib import Path
from typing import Any
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
INSECURE_SECRET = "changeme"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", case_sensitive=True, extra="ignore"
    )

    PROJECT_NAME: str = "Terminator"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["local", "production"] = "local"

    SECRET_KEY: str = INSECURE_SECRET
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    # Long-lived so an installed PWA that was offline for a while can still sync.
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str = "terminator"
    POSTGRES_PORT: int = 5432
    # A full connection string (e.g. Neon's) overrides the POSTGRES_* parts.
    DATABASE_URL: str = ""

    # Google Sign-In is enabled only when this looks like a real OAuth client id.
    GOOGLE_CLIENT_ID: str = ""
    # Admins (comma-separated emails): always allowed, and they choose who else may
    # use the app (in the app, stored in the database). Empty: anyone who can sign in.
    ADMIN_EMAILS: str = ""

    # Spotify playback controls while logging (a Spotify app's client id; the
    # browser signs in with PKCE, so no secret). Empty: the feature is hidden.
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_ACCOUNTS_URL: str = "https://accounts.spotify.com"  # overridden in tests

    # Passwordless "log in as the dev user" button. Defaults to on only for local.
    DEV_LOGIN_ENABLED: bool | None = None

    BACKEND_CORS_ORIGINS: list[str] = []

    # Built PWA served by FastAPI when present (single-origin deploy).
    FRONTEND_DIST: Path = REPO_ROOT / "frontend" / "dist"

    @property
    def serverless(self) -> bool:
        """On Vercel: every instance is short-lived, so no connection pool."""
        return bool(os.environ.get("VERCEL"))

    @property
    def database_url(self) -> URL:
        if self.DATABASE_URL:
            url = make_url(self.DATABASE_URL).set(drivername="postgresql+asyncpg")
            # libpq options asyncpg doesn't understand; SSL goes in connect_args.
            return url.difference_update_query(["sslmode", "channel_binding"])
        return URL.create(
            "postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD or None,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            database=self.POSTGRES_DB,
        )

    @property
    def database_connect_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {}
        url = make_url(self.DATABASE_URL) if self.DATABASE_URL else None
        if url and (url.query.get("sslmode", "") not in ("", "disable") or (url.host or "").endswith(".neon.tech")):
            args["ssl"] = True
        if self.serverless or (url and "-pooler" in (url.host or "")):
            # PgBouncer (Neon's pooler) in transaction mode can't keep prepared statements.
            args["statement_cache_size"] = 0
        return args

    @property
    def dev_login_enabled(self) -> bool:
        if self.DEV_LOGIN_ENABLED is None:
            return self.ENVIRONMENT == "local"
        return self.DEV_LOGIN_ENABLED

    @property
    def admin_emails(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.ADMIN_EMAILS.split(",") if e.strip())

    @property
    def access_restricted(self) -> bool:
        return bool(self.admin_emails)

    def is_admin(self, email: str) -> bool:
        return email.strip().lower() in self.admin_emails

    @property
    def google_login_enabled(self) -> bool:
        return self.GOOGLE_CLIENT_ID.endswith(".apps.googleusercontent.com")

    @model_validator(mode="after")
    def _check_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.SECRET_KEY == INSECURE_SECRET or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be set to 32+ random characters in production")
            if self.DEV_LOGIN_ENABLED:
                raise ValueError("DEV_LOGIN_ENABLED must not be on in production")
        return self


settings = Settings()
