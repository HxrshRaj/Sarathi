"""GitHub client. OAuth + REST calls made with the user's stored token.

The token is passed here out-of-band from the DB — it is never placed in an LLM
prompt and never returned by an API response.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings
from app.errors import AppError, ErrorCategory
from app.logging import get_logger

log = get_logger("github")

_GH_API = "https://api.github.com"
_GH_OAUTH = "https://github.com/login/oauth"
_UA = "CodePilot/0.1"


@dataclass(slots=True)
class GithubUser:
    id: int
    login: str
    name: str | None
    avatar_url: str | None


def oauth_authorize_url(state: str) -> str:
    s = get_settings()
    scopes = "%20".join(s.github_scope_list)
    redirect = f"{s.api_base_url}/api/auth/github/callback"
    return (
        f"{_GH_OAUTH}/authorize?client_id={s.github_client_id}"
        f"&redirect_uri={redirect}&scope={scopes}&state={state}&allow_signup=false"
    )


def new_state() -> str:
    return secrets.token_urlsafe(24)


async def exchange_code(code: str) -> tuple[str, list[str]]:
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{_GH_OAUTH}/access_token",
            headers={"Accept": "application/json", "User-Agent": _UA},
            data={
                "client_id": s.github_client_id,
                "client_secret": s.github_client_secret,
                "code": code,
                "redirect_uri": f"{s.api_base_url}/api/auth/github/callback",
            },
        )
    payload = resp.json()
    if "access_token" not in payload:
        raise AppError(
            ErrorCategory.AUTH,
            "GitHub OAuth exchange failed",
            detail={"github_error": payload.get("error", "unknown")},
        )
    return payload["access_token"], payload.get("scope", "").split(",")


class GithubClient:
    def __init__(self, token: str) -> None:
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": _UA,
        }

    async def _get(self, path: str, **params: Any) -> Any:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{_GH_API}{path}", headers=self._headers(), params=params)
        if resp.status_code == 401:
            raise AppError(ErrorCategory.AUTH, "GitHub token rejected", detail={"path": path})
        if resp.status_code >= 400:
            raise AppError(
                ErrorCategory.INFRA,
                "GitHub API error",
                detail={"path": path, "status": resp.status_code},
                retryable=resp.status_code >= 500,
            )
        return resp.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(f"{_GH_API}{path}", headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise AppError(
                ErrorCategory.INFRA,
                "GitHub API write failed",
                detail={"path": path, "status": resp.status_code, "body": resp.text[:500]},
                retryable=resp.status_code >= 500,
            )
        return resp.json()

    async def current_user(self) -> GithubUser:
        d = await self._get("/user")
        return GithubUser(
            id=d["id"], login=d["login"], name=d.get("name"), avatar_url=d.get("avatar_url")
        )

    async def list_repos(self, per_page: int = 100) -> list[dict[str, Any]]:
        repos: list[dict[str, Any]] = []
        page = 1
        while page <= 5:
            batch = await self._get(
                "/user/repos",
                per_page=per_page,
                page=page,
                sort="updated",
                affiliation="owner,collaborator",
            )
            repos.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
        return [
            {
                "github_repo_id": r["id"],
                "full_name": r["full_name"],
                "default_branch": r["default_branch"],
                "private": r["private"],
                "clone_url": r["clone_url"],
                "updated_at": r["updated_at"],
            }
            for r in repos
        ]

    async def list_branches(self, full_name: str) -> list[str]:
        data = await self._get(f"/repos/{full_name}/branches", per_page=100)
        return [b["name"] for b in data]

    async def default_branch_head(self, full_name: str, branch: str) -> str:
        data = await self._get(f"/repos/{full_name}/commits/{branch}")
        return data["sha"]

    async def create_pull_request(
        self, full_name: str, *, head: str, base: str, title: str, body: str, draft: bool = False
    ) -> dict[str, Any]:
        return await self._post(
            f"/repos/{full_name}/pulls",
            {"head": head, "base": base, "title": title, "body": body, "draft": draft},
        )
