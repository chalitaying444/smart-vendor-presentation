"""ธุรกิจ/ตรรกะเกี่ยวกับ collection `users`."""
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId

from app.core.config import settings
from app.db.mongodb import users_collection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def to_object_id(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise ValueError("รูปแบบ id ไม่ถูกต้อง") from exc


async def get_by_id(user_id: str) -> Optional[dict[str, Any]]:
    return await users_collection().find_one({"_id": to_object_id(user_id)})


async def get_by_email(email: str) -> Optional[dict[str, Any]]:
    return await users_collection().find_one({"email": email.lower()})


async def get_by_ms_oid(oid: str) -> Optional[dict[str, Any]]:
    return await users_collection().find_one({"ms_oid": oid})


async def list_users(skip: int = 0, limit: int = 50, q: Optional[str] = None) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if q:
        query = {"$or": [
            {"email": {"$regex": q, "$options": "i"}},
            {"display_name": {"$regex": q, "$options": "i"}},
            {"vendor_code": {"$regex": q, "$options": "i"}},
        ]}
    cursor = users_collection().find(query).sort("created_at", -1).skip(skip).limit(limit)
    return [doc async for doc in cursor]


async def count_users(q: Optional[str] = None) -> int:
    query: dict[str, Any] = {}
    if q:
        query = {"$or": [
            {"email": {"$regex": q, "$options": "i"}},
            {"display_name": {"$regex": q, "$options": "i"}},
        ]}
    return await users_collection().count_documents(query)


async def create_user(payload: dict[str, Any]) -> dict[str, Any]:
    doc = {
        "email": payload["email"].lower(),
        "display_name": payload.get("display_name"),
        "role": payload.get("role", "vendor"),
        "vendor_code": payload.get("vendor_code"),
        # หน่วยงานที่สังกัด — ตัวกำหนดว่าเห็นโครงการไหนได้ (services/bom_access.py)
        "departments": [str(d).strip() for d in (payload.get("departments") or []) if str(d).strip()],
        "is_active": payload.get("is_active", True),
        "auth_provider": payload.get("auth_provider", "microsoft"),
        "ms_oid": payload.get("ms_oid"),
        "ms_tenant_id": payload.get("ms_tenant_id"),
        "last_login_at": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    result = await users_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def update_user(user_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    changes = {k: v for k, v in payload.items() if v is not None}
    if "departments" in changes:
        # ส่งลิสต์ว่างมาได้ = ถอดออกจากทุกหน่วยงาน จึงต้องไม่ถูกกรองทิ้งเหมือน None
        changes["departments"] = [str(d).strip() for d in changes["departments"] if str(d).strip()]
    if not changes:
        return await get_by_id(user_id)
    changes["updated_at"] = _now()
    return await users_collection().find_one_and_update(
        {"_id": to_object_id(user_id)},
        {"$set": changes},
        return_document=True,
    )


async def delete_user(user_id: str) -> bool:
    result = await users_collection().delete_one({"_id": to_object_id(user_id)})
    return result.deleted_count == 1


async def upsert_from_microsoft(claims: dict[str, Any], graph: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """สร้าง/อัปเดตผู้ใช้จากข้อมูลที่ได้จาก Microsoft Entra ID"""
    graph = graph or {}
    oid = claims.get("oid") or claims.get("sub")
    email = (
        claims.get("email")
        or claims.get("preferred_username")
        or graph.get("mail")
        or graph.get("userPrincipalName")
        or ""
    ).lower()
    if not email:
        raise ValueError("ไม่พบอีเมลใน token ของ Microsoft")

    display_name = claims.get("name") or graph.get("displayName") or email.split("@")[0]
    tenant_id = claims.get("tid")

    existing = await get_by_ms_oid(oid) if oid else None
    if existing is None:
        existing = await get_by_email(email)

    now = _now()
    if existing:
        await users_collection().update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "email": email,
                "display_name": display_name,
                "ms_oid": oid,
                "ms_tenant_id": tenant_id,
                "auth_provider": "microsoft",
                "last_login_at": now,
                "updated_at": now,
            }},
        )
        return await users_collection().find_one({"_id": existing["_id"]})

    role = "admin" if email in settings.admin_email_list else "vendor"
    # ผู้ใช้คนแรกของระบบให้เป็น admin โดยอัตโนมัติ
    if await users_collection().count_documents({}) == 0:
        role = "admin"

    doc = await create_user({
        "email": email,
        "display_name": display_name,
        "role": role,
        "ms_oid": oid,
        "ms_tenant_id": tenant_id,
        "auth_provider": "microsoft",
    })
    await users_collection().update_one({"_id": doc["_id"]}, {"$set": {"last_login_at": now}})
    doc["last_login_at"] = now
    return doc


async def distinct_departments() -> list:
    """หน่วยงานทั้งหมดที่มีคนสังกัดอยู่จริง"""
    values = await users_collection().distinct("departments")
    return [str(v) for v in values if str(v or "").strip()]
