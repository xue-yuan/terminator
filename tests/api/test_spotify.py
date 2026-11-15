from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import settings
from app.models.spotify import SpotifyLink
from app.services.spotify import SpotifyError, SpotifyService, _challenge
from tests.conftest import TestSession

pytestmark = pytest.mark.anyio


def test_pkce_challenge_matches_rfc7636():
    assert _challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


@pytest.fixture
def spotify(monkeypatch):
    """Spotify configured, with its token endpoint faked."""
    monkeypatch.setattr(settings, "SPOTIFY_CLIENT_ID", "spotify-client")
    calls = []
    fail = {"refresh": False}

    async def token_request(self, data):
        calls.append(data)
        if data["grant_type"] == "refresh_token" and fail["refresh"]:
            raise SpotifyError("Spotify refused (400)")
        n = len(calls)
        return {"access_token": f"access-{n}", "refresh_token": f"refresh-{n}", "expires_in": 3600}

    monkeypatch.setattr(SpotifyService, "_token_request", token_request)
    return {"calls": calls, "fail": fail}


async def connect(client, user) -> dict:
    r = await client.post("/api/v1/spotify/connect", json={"origin": "http://127.0.0.1:5173"}, headers=user["headers"])
    assert r.status_code == 200, r.text
    return {k: v[0] for k, v in parse_qs(urlparse(r.json()["url"]).query).items()}


async def test_hidden_when_not_configured(client, user):
    r = await client.get("/api/v1/spotify/status", headers=user["headers"])
    assert r.json() == {"configured": False, "connected": False}
    r = await client.post("/api/v1/spotify/connect", json={"origin": "http://127.0.0.1:5173"}, headers=user["headers"])
    assert r.status_code == 404


async def test_sign_in_then_tokens(client, user, spotify):
    query = await connect(client, user)
    assert query["client_id"] == "spotify-client"
    assert query["redirect_uri"] == "http://127.0.0.1:5173/api/v1/spotify/callback"
    assert query["code_challenge_method"] == "S256" and query["code_challenge"]
    assert "user-modify-playback-state" in query["scope"]

    r = await client.get("/api/v1/spotify/callback", params={"state": query["state"], "code": "the-code"})
    assert (r.status_code, r.headers["location"]) == (303, "/spotify/done?connected=1")  # back into the app
    exchange = spotify["calls"][0]
    assert exchange["grant_type"] == "authorization_code" and exchange["code"] == "the-code"
    assert _challenge(exchange["code_verifier"]) == query["code_challenge"]  # PKCE pair matches

    r = await client.get("/api/v1/spotify/status", headers=user["headers"])
    assert r.json() == {"configured": True, "connected": True}
    r = await client.post("/api/v1/spotify/token", headers=user["headers"])
    assert r.json()["access_token"] == "access-1"
    assert len(spotify["calls"]) == 1  # still valid: no refresh

    # the same state can't be used twice
    r = await client.get("/api/v1/spotify/callback", params={"state": query["state"], "code": "again"})
    assert r.headers["location"] == "/spotify/done?error=expired"


async def test_expired_tokens_are_refreshed_and_a_dead_refresh_token_disconnects(client, user, spotify):
    query = await connect(client, user)
    await client.get("/api/v1/spotify/callback", params={"state": query["state"], "code": "c"})
    async with TestSession() as s:
        link = await s.get(SpotifyLink, user["id"])
        link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    r = await client.post("/api/v1/spotify/token", headers=user["headers"])
    assert r.json()["access_token"] == "access-2"
    assert spotify["calls"][-1] == {"grant_type": "refresh_token", "refresh_token": "refresh-1"}

    async with TestSession() as s:
        link = await s.get(SpotifyLink, user["id"])
        link.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    spotify["fail"]["refresh"] = True
    r = await client.post("/api/v1/spotify/token", headers=user["headers"])
    assert r.status_code == 409
    r = await client.get("/api/v1/spotify/status", headers=user["headers"])
    assert r.json()["connected"] is False


async def test_failed_token_exchange_says_so(client, user, spotify, monkeypatch):
    query = await connect(client, user)

    async def refuse(self, data):
        raise SpotifyError("Spotify refused (400)")

    monkeypatch.setattr(SpotifyService, "_token_request", refuse)
    r = await client.get("/api/v1/spotify/callback", params={"state": query["state"], "code": "c"})
    assert r.headers["location"] == "/spotify/done?error=failed"


async def test_callback_errors_and_disconnect(client, user, spotify):
    r = await client.get("/api/v1/spotify/callback", params={"error": "access_denied"})
    assert r.headers["location"] == "/spotify/done?error=denied"
    r = await client.get("/api/v1/spotify/callback", params={"state": "made-up", "code": "c"})
    assert r.headers["location"] == "/spotify/done?error=expired"

    query = await connect(client, user)
    await client.get("/api/v1/spotify/callback", params={"state": query["state"], "code": "c"})
    assert (await client.delete("/api/v1/spotify", headers=user["headers"])).status_code == 204
    assert (await client.get("/api/v1/spotify/status", headers=user["headers"])).json()["connected"] is False
    assert (await client.post("/api/v1/spotify/token", headers=user["headers"])).status_code == 409


async def test_origin_must_be_an_origin(client, user, spotify):
    for origin in ("javascript:alert(1)", "http://evil.example/path", "ftp://x"):
        r = await client.post("/api/v1/spotify/connect", json={"origin": origin}, headers=user["headers"])
        assert r.status_code == 422, origin
