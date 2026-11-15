import uuid

import pytest

pytestmark = pytest.mark.anyio


def entry(day: int, weight: float, unit: str = "kg") -> dict:
    return {"measured_at": f"2026-11-{day:02d}T07:30:00Z", "weight": weight, "unit": unit}


async def test_upsert_list_and_delete(client, user, make_user):
    url = f"/api/v1/body-weights/{uuid.uuid4()}"
    r = await client.put(url, json=entry(1, 80.4), headers=user["headers"])
    assert r.status_code == 201, r.text
    r = await client.put(url, json=entry(1, 80.2), headers=user["headers"])  # retried / corrected
    assert (r.status_code, r.json()["weight"]) == (200, 80.2)
    await client.put(f"/api/v1/body-weights/{uuid.uuid4()}", json=entry(8, 176, "lb"), headers=user["headers"])

    r = await client.get("/api/v1/body-weights/", headers=user["headers"])
    assert [(e["weight"], e["unit"]) for e in r.json()] == [(176, "lb"), (80.2, "kg")]  # newest first

    other = await make_user(email="t1000@example.com")
    assert (await client.get("/api/v1/body-weights/", headers=other["headers"])).json() == []
    assert (await client.put(url, json=entry(2, 1), headers=other["headers"])).status_code == 404
    assert (await client.delete(url, headers=other["headers"])).status_code == 204  # not theirs: no-op

    assert (await client.delete(url, headers=user["headers"])).status_code == 204
    assert (await client.delete(url, headers=user["headers"])).status_code == 204
    assert len((await client.get("/api/v1/body-weights/", headers=user["headers"])).json()) == 1


@pytest.mark.parametrize(
    "bad",
    [{"weight": 0}, {"unit": "stone"}, {"measured_at": "2026-11-01T07:30:00"}],
    ids=["zero", "unit", "naive-time"],
)
async def test_validation(client, user, bad):
    r = await client.put(f"/api/v1/body-weights/{uuid.uuid4()}", json=entry(1, 80) | bad, headers=user["headers"])
    assert r.status_code == 422
