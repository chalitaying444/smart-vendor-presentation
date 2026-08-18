"""Dependencies: ดึงผู้ใช้ปัจจุบันจาก cookie หรือ Authorization header"""
from typing import Any, Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.core.security import decode_access_token
from app.services import user_service

bearer_scheme = HTTPBearer(auto_error=False, description="ใส่ JWT ที่ได้จาก /auth/ms/callback")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    vendor_session: Optional[str] = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
) -> dict[str, Any]:
    token = credentials.credentials if credentials else vendor_session
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ยังไม่ได้เข้าสู่ระบบ")

    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "โทเคนไม่ถูกต้อง")

    user = await user_service.get_by_id(payload.get("sub", ""))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "ไม่พบผู้ใช้")
    if not user.get("is_active", True):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "บัญชีนี้ถูกระงับการใช้งาน")
    return user


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ต้องมีสิทธิ์ admin เท่านั้น")
    return user


# ---------------------------------------------------------------------------
# ระดับสิทธิ์สำหรับงาน sourcing (BOM / RFQ)
#
#   viewer  ดูอย่างเดียว
#   buyer   นำเข้า BOM, จับคู่สินค้า, ออกและส่ง RFQ
#   admin   ทุกอย่าง รวมถึงอนุมัติผู้ขายและลบข้อมูล
#
# role ที่ไม่รู้จักถือเป็น viewer เพื่อไม่ให้เผลอได้สิทธิ์เขียนโดยไม่ตั้งใจ
#
# "staff" กับ "buyer" คือระดับเดียวกัน — หน้าจัดการผู้ใช้เดิมใช้คำว่า staff
# ส่วนโค้ดฝั่ง sourcing ใช้คำว่า buyer ถ้าไม่ใส่ทั้งคู่ไว้ คนที่ถูกตั้งเป็น staff
# จะกลายเป็น viewer เงียบ ๆ แล้วสร้างโครงการไม่ได้โดยไม่มีข้อความบอกว่าเพราะอะไร
# ---------------------------------------------------------------------------
ROLE_RANK = {"viewer": 1, "vendor": 1, "staff": 2, "buyer": 2, "admin": 3}


def require_role(minimum: str):
    need = ROLE_RANK[minimum]

    async def _dep(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if ROLE_RANK.get(user.get("role", "viewer"), 0) < need:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "สิทธิ์ไม่เพียงพอ — ต้องมีสิทธิ์ {} ขึ้นไป".format(minimum),
            )
        return user

    return _dep


require_buyer = require_role("buyer")
