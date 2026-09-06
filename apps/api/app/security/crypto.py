"""Symmetric encryption for OAuth tokens at rest (Fernet).

In dev/test with no ENCRYPTION_KEY set, a deterministic key derived from
SESSION_SECRET is used so the stack boots — refused when ENV=production.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings
from app.errors import AppError, ErrorCategory


def _fernet() -> Fernet:
    s = get_settings()
    if s.encryption_key:
        return Fernet(s.encryption_key.encode())
    if s.is_production:
        raise AppError(ErrorCategory.INFRA, "ENCRYPTION_KEY is required in production")
    derived = base64.urlsafe_b64encode(hashlib.sha256(s.session_secret.encode()).digest())
    return Fernet(derived)


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(token: bytes) -> str:
    try:
        return _fernet().decrypt(token).decode()
    except InvalidToken as exc:  # pragma: no cover - key rotation / corruption
        raise AppError(ErrorCategory.INFRA, "Failed to decrypt stored credential") from exc


def generate_key() -> str:
    return Fernet.generate_key().decode()
