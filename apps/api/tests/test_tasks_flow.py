from __future__ import annotations

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.enums import IndexStatus
from app.models.repository import Repository, RepositoryVersion
from app.models.user import User
from tests.conftest import requires_db

pytestmark = requires_db


async def _dev_repo() -> str:
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.github_user_id == 0))
        if user is None:
            user = User(github_user_id=0, login="dev", name="Local Dev")
            db.add(user)
            await db.flush()
        repo = Repository(
            user_id=user.id,
            github_repo_id=1,
            full_name="dev/app",
            default_branch="main",
            private=True,
            clone_url="https://x/app.git",
        )
        db.add(repo)
        await db.flush()
        db.add(
            RepositoryVersion(
                repository_id=repo.id,
                branch="main",
                commit_sha="a" * 40,
                status=IndexStatus.READY,
            )
        )
        await db.commit()
        return str(repo.id)


async def test_create_task_defaults_and_persists(client):
    repo_id = await _dev_repo()
    r = await client.post(
        "/api/tasks",
        json={
            "repository_id": repo_id,
            "branch": "main",
            "title": "Add pagination to users endpoint",
            "description": "Add limit/offset pagination without breaking callers.",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert body["autonomy"] == "supervised"
    assert body["model"]  # defaulted from settings


async def test_create_task_rejects_short_description(client):
    repo_id = await _dev_repo()
    r = await client.post(
        "/api/tasks",
        json={
            "repository_id": repo_id,
            "branch": "main",
            "title": "x too short",
            "description": "no",
        },
    )
    assert r.status_code == 422
    assert r.json()["error"]["category"] == "validation"


async def test_run_task_enqueues(monkeypatch, client):
    calls = {}

    def fake_dispatch(name, **kwargs):
        calls["name"] = name
        calls["kwargs"] = kwargs
        return "job-1"

    monkeypatch.setattr("app.routers.tasks.dispatch", fake_dispatch)

    repo_id = await _dev_repo()
    created = await client.post(
        "/api/tasks",
        json={
            "repository_id": repo_id,
            "branch": "main",
            "title": "Fix the checkout bug",
            "description": "Investigate and fix the 500 on checkout.",
        },
    )
    task_id = created.json()["id"]

    r = await client.post(f"/api/tasks/{task_id}/run")
    assert r.status_code == 202, r.text
    assert calls["name"] == "worker.run_agent_task"
    assert calls["kwargs"]["task_id"] == task_id
    assert r.json()["status"] == "running"


async def test_diff_endpoint_empty_before_run(client):
    repo_id = await _dev_repo()
    created = await client.post(
        "/api/tasks",
        json={
            "repository_id": repo_id,
            "branch": "main",
            "title": "Some engineering task",
            "description": "Do the thing described here.",
        },
    )
    task_id = created.json()["id"]
    r = await client.get(f"/api/tasks/{task_id}/diff")
    assert r.status_code == 200
    assert r.json()["files"] == []
