"""JWT ของแอปเราเอง (ออกให้หลังจากยืนยันตัวตนกับ Microsoft สำเร็จ)"""
import base64
import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt

from app.core.config import settings


def create_access_token(subject: str, extra: Optional[dict[str, Any]] = None) -> tuple[str, int]:
    """คืน (token, expires_in_seconds)"""
    expires_delta = timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        "iss": settings.APP_NAME,
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, int(expires_delta.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


# ---------- PKCE helpers สำหรับ OAuth2 Authorization Code Flow ----------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def generate_pkce_pair() -> tuple[str, str]:
    """คืน (code_verifier, code_challenge) แบบ S256"""
    verifier = _b64url(os.urandom(64))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def generate_state() -> str:
    return _b64url(os.urandom(24))
