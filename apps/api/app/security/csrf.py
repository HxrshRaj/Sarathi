"""Double-submit CSRF: a signed token in a readable cookie, echoed in a header.

The token is bound to the session id so it cannot be reused across sessions.
"""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Request

from app.config import get_settings
from app.errors import Forbidden

CSRF_COOKIE = "cp_csrf"
CSRF_HEADER = "x-csrf-token"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def issue_token(session_id: str) -> str:
    secret = get_settings().session_secret.encode()
    return hmac.new(secret, session_id.encode(), hashlib.sha256).hexdigest()


def verify(request: Request, session_id: str) -> None:
    if request.method in _SAFE_METHODS:
        return
    expected = issue_token(session_id)
    provided = request.headers.get(CSRF_HEADER, "")
    if not provided or not hmac.compare_digest(provided, expected):
        raise Forbidden("CSRF token missing or invalid")
