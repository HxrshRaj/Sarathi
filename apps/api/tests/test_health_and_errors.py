from __future__ import annotations

from tests.conftest import requires_db


async def test_health_ok(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


async def test_correlation_id_header_present(client):
    r = await client.get("/api/health")
    assert r.headers.get("x-correlation-id")


async def test_unknown_route_uses_error_envelope(client):
    r = await client.get("/api/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["category"] == "not_found"
    assert "correlation_id" in body["error"]


@requires_db
async def test_validation_error_envelope(client):
    # POST /api/tasks with a bad body -> 422 with our envelope
    r = await client.post("/api/tasks", json={"title": "x"})
    assert r.status_code == 422
    assert r.json()["error"]["category"] == "validation"
