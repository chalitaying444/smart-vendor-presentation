"""CRUD ผู้ใช้ (collection `users` ใน database `user`)"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.deps import get_current_user, require_admin
from app.models.user import MessageResponse, UserCreate, UserOut, UserUpdate, serialize_user
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


class UserListResponse(BaseModel):
    total: int
    items: list[UserOut]


@router.get("", response_model=UserListResponse, summary="รายชื่อผู้ใช้ทั้งหมด")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    q: Optional[str] = Query(None, description="ค้นหาจากอีเมล / ชื่อ / รหัสเวนเดอร์"),
    _: dict[str, Any] = Depends(require_admin),
):
    items = await user_service.list_users(skip=skip, limit=limit, q=q)
    total = await user_service.count_users(q=q)
    return {"total": total, "items": [serialize_user(i) for i in items]}


@router.get(
    "/meta/departments",
    summary="รายชื่อหน่วยงานที่มีอยู่ในระบบ",
    description=(
        "รวบรวมจากหน่วยงานที่ผู้ใช้สังกัดจริงและหน่วยงานที่โครงการใช้อยู่ · "
        "ใช้เป็นตัวเลือกให้เลือก จะได้ไม่พิมพ์ชื่อหน่วยงานเดียวกันคนละแบบ "
        "(\"ฝ่ายจัดซื้อ\" กับ \"จัดซื้อ\" จะกลายเป็นคนละหน่วยงานทันที)"
    ),
)
async def list_departments(_: dict[str, Any] = Depends(get_current_user)):
    from app.db import schema
    from app.db.mongodb import get_database

    db = get_database()
    from_users = await user_service.distinct_departments()
    from_boms = await db[schema.BOMS].distinct("department")
    names = sorted({str(d).strip() for d in (from_users + list(from_boms)) if str(d).strip()})
    return {"items": names}


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="สร้างผู้ใช้ใหม่")
async def create_user(payload: UserCreate, _: dict[str, Any] = Depends(require_admin)):
    if await user_service.get_by_email(payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "อีเมลนี้มีอยู่ในระบบแล้ว")
    doc = await user_service.create_user(payload.model_dump())
    return serialize_user(doc)


@router.get("/{user_id}", response_model=UserOut, summary="ดูข้อมูลผู้ใช้รายคน")
async def get_user(user_id: str, current: dict[str, Any] = Depends(get_current_user)):
    if current.get("role") != "admin" and str(current["_id"]) != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ดูได้เฉพาะข้อมูลของตัวเอง")
    doc = await user_service.get_by_id(user_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้")
    return serialize_user(doc)


@router.patch("/{user_id}", response_model=UserOut, summary="แก้ไขข้อมูลผู้ใช้")
async def update_user(user_id: str, payload: UserUpdate, _: dict[str, Any] = Depends(require_admin)):
    doc = await user_service.update_user(user_id, payload.model_dump(exclude_unset=True))
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้")
    return serialize_user(doc)


@router.delete("/{user_id}", response_model=MessageResponse, summary="ลบผู้ใช้")
async def delete_user(user_id: str, current: dict[str, Any] = Depends(require_admin)):
    if str(current["_id"]) == user_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ลบบัญชีตัวเองไม่ได้")
    if not await user_service.delete_user(user_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้")
    return {"detail": "ลบผู้ใช้เรียบร้อย"}
