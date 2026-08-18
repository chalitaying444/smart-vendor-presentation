"""ใครเห็นโครงการไหนได้บ้าง — กติกาเดียว ใช้ร่วมกันทุกที่

กติกา (ตกลงกับผู้ใช้ไว้):

* **ผู้ขายและรายการซื้อขายทั้งหมด ทุกคนเห็นได้** — ข้อจำกัดนี้ใช้กับ "โครงการ" เท่านั้น
* เห็นโครงการได้เมื่อเข้าเงื่อนไขข้อใดข้อหนึ่ง
  1. เป็นคนสร้างเอง
  2. โครงการนั้นเป็นของหน่วยงานที่ตัวเองสังกัด (สังกัดได้มากกว่า 1 หน่วยงาน)
  3. ถูก assign เข้าโครงการนั้นเป็นรายคน (ข้ามหน่วยงานได้)
* admin เห็นทุกโครงการ

**ตรวจที่ฐานข้อมูล ไม่ใช่ที่หน้าจอ** — ตัวกรองถูกยัดเข้าไปในคำสั่ง find ตั้งแต่ต้น
ไม่ใช่ดึงมาทั้งหมดแล้วค่อยกรองทิ้งทีหลัง เพราะถ้าลืมกรองที่ไหนสักที่
ข้อมูลจะหลุดออกไปเงียบ ๆ โดยไม่มีใครเห็น

**โครงการที่ถูกลบคือการซ่อน ไม่ใช่การทำลาย** — ตั้งค่า ``deleted_at`` ไว้
รายการที่ลบไปแล้วจะไม่โผล่ในทุกหน้าจอ แต่กู้กลับมาได้จากถังขยะ
เหตุผลที่ไม่ลบจริง: โครงการที่ออกใบขอราคาไปแล้วมีผู้ขายถือใบอยู่ข้างนอก
ลบทิ้งถาวรเสียงเสียประวัติที่ตามกลับไม่ได้
"""
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status


def departments_of(user: Dict[str, Any]) -> List[str]:
    """หน่วยงานที่ผู้ใช้คนนี้สังกัด — คนเดียวอยู่ได้หลายหน่วยงาน"""
    raw = user.get("departments")
    if isinstance(raw, str):        # เผื่อข้อมูลเก่าที่เคยเก็บเป็นข้อความเดียว
        raw = [raw]
    return [d for d in (raw or []) if str(d).strip()]


def default_department(user: Dict[str, Any]) -> str:
    """หน่วยงานตั้งต้นตอนสร้างโครงการ = หน่วยงานแรกที่สังกัด"""
    depts = departments_of(user)
    return depts[0] if depts else ""


def is_admin(user: Dict[str, Any]) -> bool:
    return user.get("role") == "admin"


def visible_filter(user: Dict[str, Any], include_deleted: bool = False) -> Dict[str, Any]:
    """เงื่อนไข Mongo ของ "โครงการที่คนนี้เห็นได้" — เอาไป $and กับเงื่อนไขค้นหาอื่น"""
    query: Dict[str, Any] = {}
    if not include_deleted:
        query["deleted_at"] = None

    if is_admin(user):
        return query

    email = user.get("email", "")
    allow: List[Dict[str, Any]] = [{"created_by": email}, {"assignees": email}]
    depts = departments_of(user)
    if depts:
        allow.append({"department": {"$in": depts}})
    query["$or"] = allow
    return query


def can_view(user: Dict[str, Any], bom: Dict[str, Any]) -> bool:
    if is_admin(user):
        return True
    email = user.get("email", "")
    if bom.get("created_by") == email or email in (bom.get("assignees") or []):
        return True
    dept = bom.get("department") or ""
    return bool(dept) and dept in departments_of(user)


def can_manage(user: Dict[str, Any], bom: Dict[str, Any]) -> bool:
    """ลบ / กู้คืน / เปลี่ยนหน่วยงาน / assign คนอื่น = เจ้าของโครงการกับ admin เท่านั้น

    คนในหน่วยงานเดียวกัน "เห็นและทำงานต่อได้" แต่ไม่ควรลบงานของคนอื่นทิ้ง
    """
    return is_admin(user) or bom.get("created_by") == user.get("email", "")


def require_view(user: Dict[str, Any], bom: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not bom:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบงานประมาณราคานี้")
    if bom.get("deleted_at") and not is_admin(user) and not can_manage(user, bom):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบงานประมาณราคานี้")
    if not can_view(user, bom):
        # บอกตรง ๆ ว่าไม่มีสิทธิ์ ไม่ใช่แกล้งบอกว่าไม่มีอยู่ — ไม่งั้นคนที่ได้ลิงก์มาจาก
        # เพื่อนร่วมงานจะนึกว่าโครงการถูกลบไปแล้ว แล้วไปสร้างใหม่ซ้ำ
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "โครงการนี้เป็นของหน่วยงาน{} — ขอให้เจ้าของโครงการเพิ่มคุณเข้าโครงการก่อน".format(
                " " + bom["department"] if bom.get("department") else "อื่น"),
        )
    return bom


def require_manage(user: Dict[str, Any], bom: Dict[str, Any]) -> Dict[str, Any]:
    require_view(user, bom)
    if not can_manage(user, bom):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "ทำได้เฉพาะเจ้าของโครงการ ({}) หรือผู้ดูแลระบบ".format(bom.get("created_by", "")),
        )
    return bom


def access_view(user: Dict[str, Any], bom: Dict[str, Any]) -> Dict[str, Any]:
    """ข้อมูลสิทธิ์ที่ส่งไปให้หน้าเว็บ — ปุ่มลบ/assign จะได้ไม่ต้องเดาเอง"""
    return {
        "department": bom.get("department", ""),
        "owner": bom.get("created_by", ""),
        "assignees": bom.get("assignees") or [],
        "can_manage": can_manage(user, bom),
        "deleted_at": bom.get("deleted_at"),
        "deleted_by": bom.get("deleted_by", ""),
    }


async def visible_bom_ids(user: Dict[str, Any]) -> Optional[List[Any]]:
    """_id ของโครงการที่คนนี้เห็นได้ — คืน None แปลว่า "เห็นได้ทุกอัน" (admin)

    ใช้กรองใบขอราคาที่ออกมาจากโครงการ ไม่งั้นข้อจำกัดจะเป็นแค่การซ่อนหน้าจอเดียว:
    ชื่อโครงการกับราคาจะไปโผล่ในรายการใบขอราคาให้คนที่ไม่ควรเห็นอยู่ดี
    """
    if is_admin(user):
        return None

    from app.db import schema
    from app.db.mongodb import get_database

    docs = await get_database()[schema.BOMS].find(
        visible_filter(user, include_deleted=True), {"_id": 1}
    ).to_list(None)
    return [d["_id"] for d in docs]
