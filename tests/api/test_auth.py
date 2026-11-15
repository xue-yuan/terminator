import httpx
import pytest

from app.core import security
from app.core.config import settings
from app.services.auth import AuthService

pytestmark = pytest.mark.anyio


async def test_auth_config(client):
    r = await client.get("/api/v1/auth/config")
    assert r.status_code == 200
    assert r.json() == {
        "google_client_id": "test-client.apps.googleusercontent.com",
        "dev_login_enabled": True,
        "spotify_client_id": None,
    }


async def test_auth_config_offers_spotify_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "SPOTIFY_CLIENT_ID", "spotify-client")
    r = await client.get("/api/v1/auth/config")
    assert r.json()["spotify_client_id"] == "spotify-client"


async def test_dev_login_then_me(client):
    r = await client.post("/api/v1/auth/login/dev")
    assert r.status_code == 200
    tokens = r.json()
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "dev@terminator.fit"

    # Logging in again reuses the same user
    again = await client.post("/api/v1/auth/login/dev")
    assert security.decode_token(again.json()["access_token"], "access") == me.json()["id"]


async def test_dev_login_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "DEV_LOGIN_ENABLED", False)
    assert (await client.post("/api/v1/auth/login/dev")).status_code == 404
    assert (await client.get("/api/v1/auth/config")).json()["dev_login_enabled"] is False


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"}],
    ids=["missing", "garbage", "wrong-scheme"],
)
async def test_protected_routes_return_401(client, headers):
    r = await client.get("/api/v1/workouts/", headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_refresh_token_is_not_an_access_token(client, user):
    refresh = security.create_refresh_token(user["id"])
    r = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {refresh}"})
    assert r.status_code == 401


async def test_refresh_issues_new_pair(client, user):
    refresh = security.create_refresh_token(user["id"])
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert security.decode_token(r.json()["access_token"], "access") == user["id"]
    assert security.decode_token(r.json()["refresh_token"], "refresh") == user["id"]


async def test_refresh_rejects_access_token(client, user):
    access = security.create_access_token(user["id"])
    r = await client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


def _google(monkeypatch, **overrides):
    data = {
        "aud": "test-client.apps.googleusercontent.com",
        "iss": "https://accounts.google.com",
        "sub": "google-123",
        "email": "kyle@example.com",
        "email_verified": "true",
        "name": "Kyle Reese",
    } | overrides

    async def fake_tokeninfo(self, id_token):
        return data

    monkeypatch.setattr(AuthService, "_tokeninfo", fake_tokeninfo)


async def test_google_login_creates_user(client, monkeypatch):
    _google(monkeypatch)
    r = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert r.status_code == 200
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    assert me.json()["email"] == "kyle@example.com"
    assert me.json()["full_name"] == "Kyle Reese"


async def test_google_login_links_existing_email(client, monkeypatch, make_user):
    existing = await make_user(email="kyle@example.com", name="Kyle")
    _google(monkeypatch)
    r = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert security.decode_token(r.json()["access_token"], "access") == existing["id"]


@pytest.mark.parametrize(
    "overrides",
    [{"aud": "someone-else"}, {"email_verified": "false"}, {"iss": "evil.example.com"}],
    ids=["wrong-audience", "unverified-email", "wrong-issuer"],
)
async def test_google_login_rejects_bad_tokens(client, monkeypatch, overrides):
    _google(monkeypatch, **overrides)
    r = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert r.status_code == 401


async def test_google_unreachable_is_503_not_500(client, monkeypatch):
    async def unreachable(self, *args, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(httpx.AsyncClient, "get", unreachable)
    r = await client.post("/api/v1/auth/google", json={"id_token": "x"})
    assert r.status_code == 503
