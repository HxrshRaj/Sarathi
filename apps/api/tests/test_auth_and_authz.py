from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.repository import Repository
from app.models.user import User
from tests.conftest import requires_db

pytestmark = requires_db


async def test_dev_bypass_me(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert body["login"] == "dev"
    assert body["auth_mode"] == "dev"
    assert body["csrf_token"]


async def _other_users_repo() -> uuid.UUID:
    async with AsyncSessionLocal() as db:
        other = User(github_user_id=999, login="mallory")
        db.add(other)
        await db.flush()
        repo = Repository(
            user_id=other.id, github_repo_id=42, full_name="mallory/secret",
            default_branch="main", private=True, clone_url="https://x/y.git",
        )
        db.add(repo)
        await db.commit()
        return repo.id


async def test_cross_tenant_repo_is_404_not_403(client):
    other_repo_id = await _other_users_repo()
    r = await client.get(f"/api/repositories/{other_repo_id}")
    assert r.status_code == 404
    assert r.json()["error"]["category"] == "not_found"


async def test_cross_tenant_task_is_404(client):
    r = await client.get(f"/api/tasks/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_list_repositories_only_returns_own(client):
    await _other_users_repo()
    r = await client.get("/api/repositories")
    assert r.status_code == 200
    assert r.json() == []  # dev user owns none


async def test_dashboard_reports_insufficient_data(client):
    r = await client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert body["enough_data"] is False
    assert body["task_success_rate"] is None
