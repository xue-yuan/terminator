import pytest

from app.core import security
from app.core.config import settings
from app.models import AllowedEmail
from tests.conftest import TestSession

pytestmark = pytest.mark.anyio


@pytest.fixture
async def admin(make_user, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_EMAILS", "boss@example.com, other-admin@example.com")
    return await make_user(email="Boss@example.com", name="Boss")


async def test_admin_lets_people_in_and_takes_them_off(client, admin, make_user):
    url = "/api/v1/admin/access"
    r = await client.get(url, headers=admin["headers"])
    assert r.json() == {"restricted": True, "admins": ["boss@example.com", "other-admin@example.com"], "allowed": []}

    r = await client.post(url, json={"email": "  Sarah.Connor@Example.com "}, headers=admin["headers"])
    assert r.status_code == 201
    assert [(e["email"], e["signed_up"]) for e in r.json()["allowed"]] == [("sarah.connor@example.com", False)]
    assert (await client.post(url, json={"email": "sarah.connor@example.com"}, headers=admin["headers"])).status_code == 200

    sarah = await make_user(email="sarah.connor@example.com")  # she signs in
    assert (await client.get("/api/v1/users/me", headers=sarah["headers"])).status_code == 200
    r = await client.get(url, headers=admin["headers"])
    assert r.json()["allowed"][0]["signed_up"] is True

    refresh = security.create_refresh_token(sarah["id"])
    r = await client.delete(f"{url}/Sarah.Connor@example.com", headers=admin["headers"])
    assert r.json()["allowed"] == []
    assert (await client.get("/api/v1/users/me", headers=sarah["headers"])).status_code == 401  # signed out
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})).status_code == 401
    assert (await client.delete(f"{url}/sarah.connor@example.com", headers=admin["headers"])).status_code == 200


async def test_only_admins_manage_access(client, admin, make_user):
    async with TestSession() as s:
        s.add(AllowedEmail(email="john@example.com"))
        await s.commit()
    john = await make_user(email="john@example.com")
    for method, path, body in (("get", "", None), ("post", "", {"email": "x@example.com"}), ("delete", "/x@example.com", None)):
        kwargs = {"headers": john["headers"]} | ({"json": body} if body else {})
        r = await getattr(client, method)(f"/api/v1/admin/access{path}", **kwargs)
        assert r.status_code == 403, (method, path)


async def test_admin_emails_and_bad_emails_are_refused(client, admin):
    url = "/api/v1/admin/access"
    r = await client.post(url, json={"email": "other-admin@example.com"}, headers=admin["headers"])
    assert r.status_code == 409
    assert (await client.post(url, json={"email": "not an email"}, headers=admin["headers"])).status_code == 422


async def test_underscore_is_not_a_wildcard(client, admin, make_user):
    url = "/api/v1/admin/access"
    await client.post(url, json={"email": "john_doe@example.com"}, headers=admin["headers"])
    await make_user(email="johnxdoe@example.com")
    r = await client.get(url, headers=admin["headers"])
    assert r.json()["allowed"][0]["signed_up"] is False
