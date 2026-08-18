"""เส้นทางการยืนยันตัวตนด้วย Microsoft Entra ID (OpenID Connect + PKCE)"""
import logging
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.core.security import create_access_token, generate_pkce_pair, generate_state
from app.models.user import MessageResponse, TokenResponse, UserOut, serialize_user
from app.services import ms_oauth, user_service
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE = "ms_oauth_state"
VERIFIER_COOKIE = "ms_oauth_verifier"


def _set_temp_cookie(response: Response, key: str, value: str) -> None:
    response.set_cookie(
        key=key,
        value=value,
        max_age=600,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


@router.get(
    "/ms/login",
    summary="เริ่มขั้นตอนล็อกอินด้วย Microsoft",
    description="สร้าง state + PKCE แล้ว redirect ไปหน้า login ของ Microsoft Entra ID",
)
async def ms_login(redirect: bool = Query(True, description="True = redirect ทันที, False = คืน URL เป็น JSON")):
    if not settings.ms_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ยังไม่ได้ตั้งค่า MS_TENANT_ID / MS_CLIENT_ID / MS_CLIENT_SECRET ใน .env",
        )
    state = generate_state()
    verifier, challenge = generate_pkce_pair()
    url = ms_oauth.build_authorize_url(state, challenge)

    response: Response = RedirectResponse(url, status_code=status.HTTP_302_FOUND) if redirect else Response(
        content=f'{{"authorize_url":"{url}"}}', media_type="application/json"
    )
    _set_temp_cookie(response, STATE_COOKIE, state)
    _set_temp_cookie(response, VERIFIER_COOKIE, verifier)
    return response


@router.get(
    "/ms/callback",
    summary="Callback จาก Microsoft",
    description="แลก authorization code เป็น token, ตรวจสอบ id_token, บันทึกผู้ใช้ลง MongoDB แล้วออก session cookie",
)
async def ms_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
    ms_oauth_state: Optional[str] = Cookie(default=None, alias=STATE_COOKIE),
    ms_oauth_verifier: Optional[str] = Cookie(default=None, alias=VERIFIER_COOKIE),
):
    if error:
        msg = error_description or error
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?{urlencode({'error': msg})}")

    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่พบ authorization code")

    # แยกสองกรณีที่หน้าตาเหมือนกันแต่คนละสาเหตุ:
    #
    #   ไม่มีคุกกี้เลย   = เบราว์เซอร์ไม่ได้ส่งกลับมา — เกือบทุกครั้งเกิดจาก "เริ่มล็อกอิน
    #                     จากที่อยู่หนึ่ง แล้วไมโครซอฟท์ส่งกลับมาอีกที่อยู่หนึ่ง"
    #                     (เช่นกดล็อกอินที่ http://localhost:3000 แต่ MS_REDIRECT_URI
    #                     ชี้ไปโดเมน ngrok) หรือ COOKIE_SECURE=true แต่เปิดเว็บผ่าน http
    #                     ซึ่งเบราว์เซอร์จะทิ้งคุกกี้ Secure ทันทีโดยไม่เตือนอะไรเลย
    #   มีแต่ไม่ตรง      = ของปลอม/ของเก่า ค่อยเข้าข่าย CSRF จริง
    #
    # ถ้าตอบ 400 เหมือนกันหมด คนใช้จะไล่ผิดทางทุกครั้ง จึงต้องบอกให้ตรงสาเหตุ
    # และพากลับไปหน้า login แทนที่จะทิ้งไว้ที่หน้า JSON เปล่า ๆ
    if not ms_oauth_state or not ms_oauth_verifier:
        return RedirectResponse("{}/login?{}".format(
            settings.FRONTEND_URL,
            urlencode({"error": (
                "คุกกี้ยืนยันตัวตนหายระหว่างทาง — เปิดเว็บที่ {} แล้วกดล็อกอินจากที่นั่น "
                "(ต้องเริ่มและจบที่อยู่เดียวกัน) · ถ้าเปิดผ่าน http อยู่ ให้ตั้ง COOKIE_SECURE=false"
            ).format(settings.FRONTEND_URL)}),
        ))
    if not state or state != ms_oauth_state:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "state ไม่ตรงกัน (อาจเป็น CSRF)")

    try:
        token_data = await ms_oauth.exchange_code_for_token(code, ms_oauth_verifier)
        id_token = token_data.get("id_token")
        if not id_token:
            raise ValueError("ไม่พบ id_token ในคำตอบจาก Microsoft")
        claims = ms_oauth.verify_id_token(id_token)
        graph = {}
        if token_data.get("access_token"):
            graph = await ms_oauth.fetch_graph_profile(token_data["access_token"])
        user = await user_service.upsert_from_microsoft(claims, graph)
    except Exception as exc:
        logger.exception("Microsoft login failed")
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?{urlencode({'error': str(exc)})}")

    jwt_token, expires_in = create_access_token(
        subject=str(user["_id"]),
        extra={"email": user["email"], "role": user.get("role", "vendor")},
    )

    response = RedirectResponse(f"{settings.FRONTEND_URL}/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=jwt_token,
        max_age=expires_in,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    response.delete_cookie(STATE_COOKIE, path="/")
    response.delete_cookie(VERIFIER_COOKIE, path="/")
    return response


@router.get("/me", response_model=UserOut, summary="ข้อมูลผู้ใช้ที่ล็อกอินอยู่")
async def read_me(current: dict[str, Any] = Depends(get_current_user)):
    return serialize_user(current)


@router.post("/logout", response_model=MessageResponse, summary="ออกจากระบบ")
async def logout(response: Response):
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    return {"detail": "ออกจากระบบเรียบร้อย"}


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="(สำหรับทดสอบ) ออก JWT จากอีเมลที่มีอยู่ในระบบ",
    description="ใช้เฉพาะตอน DEBUG=true เพื่อทดสอบ API ผ่าน Swagger โดยไม่ต้องผ่าน Microsoft",
)
async def dev_token(email: str = Query(..., description="อีเมลของผู้ใช้ที่มีอยู่ใน MongoDB")):
    if not settings.DEBUG:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ใช้ได้เฉพาะโหมด DEBUG")
    user = await user_service.get_by_email(email)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้นี้")
    token, expires_in = create_access_token(
        subject=str(user["_id"]),
        extra={"email": user["email"], "role": user.get("role", "vendor")},
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "user": serialize_user(user),
    }
