from __future__ import annotations

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from app.config import get_settings
from app.db import get_session
from app.deps import CurrentUser, DbSession
from app.errors import BadRequest
from app.logging import get_logger
from app.models.user import GithubIdentity, User
from app.schemas.auth import Me
from app.security.crypto import encrypt
from app.security.csrf import CSRF_COOKIE, issue_token
from app.services import github
from app.services.sessions import create_session, resolve_session, revoke_session

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth")

_STATE_COOKIE = "cp_oauth_state"


def _set_session_cookies(response: Response, session_id: str) -> None:
    s = get_settings()
    common = {
        "samesite": s.cookie_samesite,
        "secure": s.cookie_secure,
        "max_age": s.session_ttl_hours * 3600,
        "path": "/",
    }
    response.set_cookie(s.session_cookie_name, session_id, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, issue_token(session_id), httponly=False, **common)


@router.get("/github/start")
async def github_start() -> RedirectResponse:
    s = get_settings()
    if not (s.github_client_id and s.github_client_secret):
        raise BadRequest("GitHub OAuth is not configured on this deployment")
    state = github.new_state()
    resp = RedirectResponse(github.oauth_authorize_url(state))
    resp.set_cookie(
        _STATE_COOKIE,
        state,
        httponly=True,
        samesite=s.cookie_samesite,
        secure=s.cookie_secure,
        max_age=600,
        path="/",
    )
    return resp


@router.get("/github/callback")
async def github_callback(request: Request, code: str, state: str) -> RedirectResponse:
    s = get_settings()
    if request.cookies.get(_STATE_COOKIE) != state:
        raise BadRequest("OAuth state mismatch")

    token, scopes = await github.exchange_code(code)
    gh_user = await github.GithubClient(token).current_user()

    async for db in get_session():
        user = await db.scalar(select(User).where(User.github_user_id == gh_user.id))
        if user is None:
            user = User(
                github_user_id=gh_user.id,
                login=gh_user.login,
                name=gh_user.name,
                avatar_url=gh_user.avatar_url,
            )
            db.add(user)
            await db.flush()
        else:
            user.login, user.name, user.avatar_url = gh_user.login, gh_user.name, gh_user.avatar_url

        identity = await db.scalar(select(GithubIdentity).where(GithubIdentity.user_id == user.id))
        enc = encrypt(token)
        if identity is None:
            db.add(GithubIdentity(user_id=user.id, access_token_encrypted=enc, scopes=scopes))
        else:
            identity.access_token_encrypted = enc
            identity.scopes = scopes

        session = await create_session(
            db,
            user,
            user_agent=request.headers.get("user-agent"),
            ip=request.client.host if request.client else None,
        )
        await db.commit()

    resp = RedirectResponse(f"{s.web_base_url}/dashboard")
    resp.delete_cookie(_STATE_COOKIE, path="/")
    _set_session_cookies(resp, session.id)
    log.info("login", user_id=str(user.id), login=user.login)
    return resp


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def logout(request: Request, db: DbSession, _user: CurrentUser) -> Response:
    s = get_settings()
    sid = request.cookies.get(s.session_cookie_name)
    if sid:
        await revoke_session(db, sid)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    kw = {"path": "/", "samesite": s.cookie_samesite, "secure": s.cookie_secure}
    resp.delete_cookie(s.session_cookie_name, **kw)
    resp.delete_cookie(CSRF_COOKIE, **kw)
    return resp


@router.get("/me", response_model=Me)
async def me(request: Request, db: DbSession, user: CurrentUser) -> Me:
    s = get_settings()
    sid = request.cookies.get(s.session_cookie_name)
    auth_mode = "github"
    if not sid or await resolve_session(db, sid) is None:
        auth_mode = "dev"
        sid = "dev-session"
    return Me(
        id=user.id,
        login=user.login,
        name=user.name,
        avatar_url=user.avatar_url,
        default_autonomy=user.default_autonomy,
        csrf_token=issue_token(sid),
        auth_mode=auth_mode,
    )
