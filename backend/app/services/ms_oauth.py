"""Microsoft Entra ID (Azure AD) OpenID Connect helpers."""
import logging
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings

logger = logging.getLogger(__name__)

_jwk_client: Optional[PyJWKClient] = None
_jwk_client_created_at: float = 0.0
_JWKS_TTL = 60 * 60  # refresh ทุก 1 ชั่วโมง


def _get_jwk_client() -> PyJWKClient:
    global _jwk_client, _jwk_client_created_at
    if _jwk_client is None or (time.time() - _jwk_client_created_at) > _JWKS_TTL:
        _jwk_client = PyJWKClient(settings.ms_jwks_url)
        _jwk_client_created_at = time.time()
    return _jwk_client


def build_authorize_url(state: str, code_challenge: str) -> str:
    params = {
        "client_id": settings.MS_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.MS_REDIRECT_URI,
        "response_mode": "query",
        "scope": " ".join(settings.scope_list),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{settings.ms_authorize_url}?{urlencode(params)}"


async def exchange_code_for_token(code: str, code_verifier: str) -> dict[str, Any]:
    data = {
        "client_id": settings.MS_CLIENT_ID,
        "client_secret": settings.MS_CLIENT_SECRET,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.MS_REDIRECT_URI,
        "code_verifier": code_verifier,
        "scope": " ".join(settings.scope_list),
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            settings.ms_token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if resp.status_code != 200:
        logger.error("Token exchange failed: %s %s", resp.status_code, resp.text)
        raise ValueError(f"แลกเปลี่ยน token กับ Microsoft ไม่สำเร็จ: {resp.text}")
    return resp.json()


def verify_id_token(id_token: str) -> dict[str, Any]:
    """ตรวจลายเซ็น id_token ด้วย public key จาก JWKS ของ Microsoft"""
    signing_key = _get_jwk_client().get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256"],
        audience=settings.MS_CLIENT_ID,
        options={"verify_iss": False},  # ตรวจเองด้านล่างเพื่อรองรับหลายรูปแบบ issuer
    )
    issuer = claims.get("iss", "")
    if settings.MS_TENANT_ID and issuer not in settings.ms_issuers:
        raise ValueError(f"issuer ไม่ถูกต้อง: {issuer}")
    return claims


async def fetch_graph_profile(access_token: str) -> dict[str, Any]:
    """ดึงข้อมูลเพิ่มเติมจาก Microsoft Graph (ถ้ามีสิทธิ์ User.Read)"""
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            "https://graph.microsoft.com/v1.0/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if resp.status_code != 200:
        logger.warning("Graph /me failed: %s %s", resp.status_code, resp.text)
        return {}
    return resp.json()
