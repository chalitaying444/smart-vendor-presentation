"""ชนิดข้อมูลและตัวช่วยที่ใช้ร่วมกันในฝั่ง sourcing (BOM / matching / RFQ)

หมายเหตุ: โปรเจกต์นี้รันบน Python 3.9 จึงใช้ Optional[...] / Union[...]
แทน syntax `Optional[X]` ที่ต้องการ 3.10 ขึ้นไป
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException, status
from pydantic import BaseModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_oid(value: str, field: str = "id") -> ObjectId:
    """แปลง string เป็น ObjectId พร้อมโยน 400 ถ้ารูปแบบผิด"""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{field} ไม่ถูกต้อง: {value}")


def serialize(doc: Any) -> Any:
    """แปลง ObjectId/datetime ในเอกสาร Mongo ให้เป็นชนิดที่ JSON รองรับ"""
    if doc is None:
        return None
    if isinstance(doc, list):
        return [serialize(d) for d in doc]
    if isinstance(doc, dict):
        out: Dict[str, Any] = {}
        for key, value in doc.items():
            out["id" if key == "_id" else key] = serialize(value)
        return out
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        if doc.tzinfo is None:
            doc = doc.replace(tzinfo=timezone.utc)
        return doc.isoformat()
    return doc


class PageResponse(BaseModel):
    """รูปแบบผลลัพธ์แบ่งหน้า — ตรงกับที่ฝั่งเดิมใช้ (total / skip / limit / has_more)"""
    total: int = 0
    skip: int = 0
    limit: int = 30
    has_more: bool = False
    items: List[Any] = []


def paged(items: List[Any], total: int, skip: int, limit: int,
          extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """extra = ข้อมูลประกอบของหน้ารายการ (เช่น หน่วยงานที่ผู้ใช้สังกัด) ส่งไปพร้อมกันครั้งเดียว"""
    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + len(items) < total,
        "items": items,
        **(extra or {}),
    }


class OkResponse(BaseModel):
    ok: bool = True
    message: str = ""
    detail: Optional[str] = None
