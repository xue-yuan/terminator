from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class GoogleLoginRequest(BaseModel):
    id_token: str


class AuthConfig(BaseModel):
    google_client_id: str | None
    dev_login_enabled: bool
    spotify_client_id: str | None
