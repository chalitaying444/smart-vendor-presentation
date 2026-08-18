"""ประมาณราคา BOM — เอารายการของโครงการมาตีงบจากราคาที่เคยซื้อจริง

ขั้นตอนที่ตั้งใจให้เป็น:
1. วางข้อความ หรืออัปโหลดไฟล์ BOM  →  ``POST /boms/parse`` ดูผลก่อนบันทึก
2. บันทึกเป็นโครงการ                →  ``POST /boms``  (ระบบจับคู่สินค้าให้อัตโนมัติ)
3. คลิกแก้ทีละบรรทัด                →  ``PATCH /boms/{id}/lines/{no}``
4. ต่อยอด                          →  ออก RFQ หรือโหลด Excel

ระบบจับคู่ให้เฉพาะที่มั่นใจพอเท่านั้น ที่เหลือปล่อยว่างไว้ให้คนเลือกเอง —
เดามั่วแล้วได้ตัวเลขงบที่ดูน่าเชื่อถือ อันตรายกว่าช่องว่างที่มองเห็น
"""
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pymongo import DESCENDING, ReturnDocument

from app.api.deps import get_current_user, require_admin, require_buyer
from app.db import schema
from app.db.mongodb import get_database
from app.models.bom import (
    BomAssignRequest,
    BomCreate,
    BomLineIn,
    BomLinePatch,
    BomParseRequest,
    BomAwardRequest,
    BomRfqPerItemRequest,
    BomRfqRequest,
    BomUpdate,
)
from app.models.common import paged, serialize, to_oid, utcnow
from app.services import bom as bom_service, bom_access, user_service
from app.services import filestore
from app.services.bom_doc import build_bom_workbook

router = APIRouter(prefix="/boms", tags=["bom-budget"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD = 5 * 1024 * 1024


async def _next_bom_no() -> str:
    year = utcnow().year
    doc = await get_database()[schema.COUNTERS].find_one_and_update(
        {"_id": "bom:{}".format(year)}, {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return "BOM-{}-{:04d}".format(year, int(doc["seq"]))


async def _get_or_404(bom_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    """ดึงโครงการ + ตรวจสิทธิ์การเห็นในที่เดียว

    ทุกเส้นทางที่แตะโครงการต้องผ่านฟังก์ชันนี้ ถ้าแยกกันตรวจ เดี๋ยวจะมีสักเส้นทาง
    ที่ลืมตรวจแล้วข้อมูลหลุดโดยไม่มีใครสังเกต
    """
    doc = await get_database()[schema.BOMS].find_one({"_id": to_oid(bom_id, "bom_id")})
    return bom_access.require_view(user, doc)


def num_or(value: int) -> str:
    return "{:,}".format(value)


async def _stamp_project(rfq: Dict[str, Any], bom: Dict[str, Any]) -> None:
    """ผูกใบขอราคากลับไปที่โครงการที่ออกมัน

    จำเป็นเพราะสิทธิ์การเห็นถูกกำหนดที่โครงการ ถ้าใบไม่รู้ว่ามาจากโครงการไหน
    ชื่อโครงการกับราคาจะไปโผล่ในรายการใบขอราคาให้คนที่ไม่มีสิทธิ์เห็นโครงการนั้น
    """
    await get_database()[schema.RFQS].update_one(
        {"_id": ObjectId(rfq["id"])},
        {"$set": {"bom_id": bom["_id"], "bom_no": bom.get("bom_no", ""),
                  "department": bom.get("department", "")}},
    )


async def _save_and_view(oid: ObjectId, changes: Dict[str, Any],
                         user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """บันทึกแล้วคำนวณใหม่ พร้อมเก็บยอดรวมไว้ให้หน้ารายการใช้โดยไม่ต้องคิดซ้ำ

    แนบข้อมูลสิทธิ์กลับไปด้วยทุกครั้ง ไม่งั้นหน้าจอที่ใช้ผลลัพธ์นี้ไปวาดใหม่
    จะเห็นว่า can_manage หายไป แล้วปุ่มลบ/จัดการสิทธิ์จะหายตามไปเฉย ๆ
    """
    db = get_database()
    changes["updated_at"] = utcnow()
    doc = await db[schema.BOMS].find_one_and_update(
        {"_id": oid}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    view = await bom_service.build_view(doc)
    # เก็บทั้งยอดรวมและสถานะไว้ให้หน้ารายการใช้ โดยไม่ต้องคิดใหม่ทุกครั้ง
    await db[schema.BOMS].update_one(
        {"_id": oid}, {"$set": {"totals": view["totals"], "progress": view["progress"]}}
    )
    if user is not None:
        view.update(bom_access.access_view(user, doc))
    return serialize(view)


# ------------------------------------------------------------------ อ่าน BOM
@router.post(
    "/parse",
    summary="แปลงข้อความ BOM ที่วางมาเป็นรายการ (ยังไม่บันทึก)",
    description="คั่นด้วย tab / , / ; / | หรือช่องว่างยาว ๆ · มีหัวตารางก็ได้ ไม่มีก็เดาให้",
)
async def parse_text(payload: BomParseRequest, _: Dict[str, Any] = Depends(get_current_user)):
    lines = bom_service.parse_text(payload.text)
    return {"lines": lines, "count": len(lines)}


@router.post(
    "/parse-file",
    summary="อ่าน BOM จากไฟล์ Excel หรือ CSV (ยังไม่บันทึก)",
)
async def parse_file(
    file: UploadFile = File(...), _: Dict[str, Any] = Depends(get_current_user)
):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "ไฟล์ใหญ่เกิน 5 MB")
    try:
        lines = bom_service.parse_upload(file.filename or "", data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if not lines:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "อ่านไฟล์แล้วไม่พบรายการ — ตรวจว่ามีคอลัมน์ชื่อรายการและจำนวนหรือไม่",
        )
    return {"lines": lines, "count": len(lines), "filename": file.filename}


# ------------------------------------------------------------------ CRUD
@router.post("", status_code=status.HTTP_201_CREATED, summary="สร้างงานประมาณราคาจาก BOM")
async def create_bom(payload: BomCreate, user: Dict[str, Any] = Depends(require_buyer)):
    if not payload.lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ต้องมีอย่างน้อย 1 รายการ")
    if len(payload.lines) > bom_service.MAX_LINES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "รับได้สูงสุด {} รายการต่อหนึ่งงาน".format(bom_service.MAX_LINES),
        )

    lines = await bom_service.match_lines([l.model_dump() for l in payload.lines])
    doc = {
        "bom_no": await _next_bom_no(),
        "title": payload.title.strip(),
        "note": payload.note.strip(),
        # หน่วยงานเจ้าของงาน — ไม่ระบุมาก็ใช้หน่วยงานแรกของคนสร้าง
        "department": (payload.department or "").strip() or bom_access.default_department(user),
        "assignees": [],
        "deleted_at": None,
        "status": "estimated",
        "currency": payload.currency,
        "contingency_percent": payload.contingency_percent,
        "vat_percent": payload.vat_percent,
        "lines": lines,
        "created_at": utcnow(),
        "created_by": user.get("email", ""),
        "updated_at": utcnow(),
    }
    result = await get_database()[schema.BOMS].insert_one(doc)
    return await _save_and_view(result.inserted_id, {}, user)


@router.get("", summary="รายการงานประมาณราคาทั้งหมด")
async def list_boms(
    q: str = Query("", description="ค้นจากชื่อโครงการหรือเลขที่"),
    mine: bool = Query(False, description="เฉพาะโครงการที่ตัวเองสร้างหรือถูก assign"),
    department: str = Query("", description="กรองเฉพาะหน่วยงานเดียว"),
    trash: bool = Query(False, description="ดูถังขยะแทนรายการปกติ"),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user),
):
    # เงื่อนไขสิทธิ์ถูกใส่ตั้งแต่ในคำสั่งค้น ไม่ใช่ดึงมาหมดแล้วค่อยกรองทิ้ง
    query: Dict[str, Any] = dict(bom_access.visible_filter(user))
    conds: List[Dict[str, Any]] = []
    if trash:
        query["deleted_at"] = {"$ne": None}
        if not bom_access.is_admin(user):
            # ถังขยะเป็นของใครของมัน — คนในหน่วยงานไม่ต้องเห็นของที่คนอื่นลบ
            query.pop("$or", None)
            conds.append({"created_by": user.get("email", "")})
    if q.strip():
        conds.append({"$or": [
            {"title": {"$regex": q.strip(), "$options": "i"}},
            {"bom_no": {"$regex": q.strip(), "$options": "i"}},
        ]})
    if mine:
        conds.append({"$or": [{"created_by": user.get("email", "")},
                              {"assignees": user.get("email", "")}]})
    if department.strip():
        conds.append({"department": department.strip()})
    if conds:
        query = {"$and": [query] + conds}
    db = get_database()
    total = await db[schema.BOMS].count_documents(query)
    docs = await db[schema.BOMS].find(query, {"lines.name": 1, "lines.part_num": 1, "title": 1,
                                              "bom_no": 1, "status": 1, "currency": 1,
                                              "totals": 1, "progress": 1, "created_at": 1, "updated_at": 1,
                                              "created_by": 1, "rfq_no": 1, "department": 1,
                                              "assignees": 1, "deleted_at": 1, "deleted_by": 1}) \
        .sort("updated_at", DESCENDING).skip(skip).limit(limit).to_list(limit)
    items = []
    for d in docs:
        row = bom_service.summary_view(d)
        row.update(bom_access.access_view(user, d))
        items.append(serialize(row))
    return paged(items, total, skip, limit,
                 extra={"departments": bom_access.departments_of(user),
                        "is_admin": bom_access.is_admin(user)})


@router.get("/{bom_id}", summary="เปิดงานประมาณราคา พร้อมยอดรวมที่คิดใหม่ล่าสุด")
async def get_bom(bom_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = await _get_or_404(bom_id, user)
    view = await bom_service.build_view(doc)
    view.update(bom_access.access_view(user, doc))
    return serialize(view)


@router.patch("/{bom_id}", summary="แก้ชื่อโครงการ / % เผื่อสำรอง / VAT")
async def update_bom(
    bom_id: str, payload: BomUpdate, user: Dict[str, Any] = Depends(require_buyer)
):
    doc = await _get_or_404(bom_id, user)
    changes = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    # ย้ายโครงการไปหน่วยงานอื่น = เปลี่ยนว่าใครเห็นได้ จึงเป็นสิทธิ์ของเจ้าของ/admin
    if "department" in changes:
        bom_access.require_manage(user, doc)
        changes["department"] = changes["department"].strip()
    if not changes:
        return serialize(await bom_service.build_view(doc))
    return await _save_and_view(doc["_id"], changes, user)


@router.delete(
    "/{bom_id}",
    summary="ลบโครงการ (ย้ายเข้าถังขยะ)",
    description=(
        "ไม่ได้ลบออกจากฐานข้อมูลจริง แต่ซ่อนจากทุกหน้าจอและกู้คืนได้ · "
        "โครงการที่ออกใบขอราคาไปแล้วมีผู้ขายถืออยู่ข้างนอก การลบถาวรจะทำให้ตามกลับไม่ได้"
    ),
)
async def delete_bom(bom_id: str, user: Dict[str, Any] = Depends(require_buyer)):
    doc = await _get_or_404(bom_id, user)
    bom_access.require_manage(user, doc)
    if doc.get("deleted_at"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "โครงการนี้อยู่ในถังขยะอยู่แล้ว")
    db = get_database()
    now = utcnow()
    await db[schema.BOMS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"deleted_at": now, "deleted_by": user.get("email", ""), "updated_at": now}},
    )
    # ใบขอราคาที่ออกจากโครงการนี้ต้องถูกยกเลิกไปด้วย ไม่ใช่ลอยค้างอยู่:
    # ถ้าปล่อยไว้ ผู้ขายที่ถือลิงก์จะยังกรอกราคาส่งเข้ามาให้โครงการที่ถูกลบแล้วได้
    # ติดธง deleted_with_bom ไว้ เพื่อตอนกู้คืนจะกู้เฉพาะใบที่หายไปเพราะโครงการนี้
    cancelled = await db[schema.RFQS].update_many(
        {"bom_id": doc["_id"], "deleted_at": None},
        {"$set": {"deleted_at": now, "deleted_by": user.get("email", ""),
                  "deleted_with_bom": True}},
    )
    count = cancelled.modified_count
    return {
        "ok": True,
        "bom_no": doc.get("bom_no", ""),
        "rfqs_cancelled": count,
        "message": "ย้าย {} เข้าถังขยะแล้ว{} — กู้คืนได้จากแท็บถังขยะ".format(
            doc.get("bom_no", ""),
            " พร้อมยกเลิกใบขอราคา {} ใบ".format(num_or(count)) if count else "",
        ),
    }


@router.post("/{bom_id}/restore", summary="กู้โครงการกลับจากถังขยะ")
async def restore_bom(bom_id: str, user: Dict[str, Any] = Depends(require_buyer)):
    doc = await _get_or_404(bom_id, user)
    bom_access.require_manage(user, doc)
    if not doc.get("deleted_at"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "โครงการนี้ไม่ได้อยู่ในถังขยะ")
    db = get_database()
    await db[schema.BOMS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"deleted_at": None, "deleted_by": "", "updated_at": utcnow()}},
    )
    restored = await db[schema.RFQS].update_many(
        {"bom_id": doc["_id"], "deleted_with_bom": True},
        {"$set": {"deleted_at": None, "deleted_by": "", "deleted_with_bom": False}},
    )
    count = restored.modified_count
    return {
        "ok": True,
        "rfqs_restored": count,
        "message": "กู้ {} กลับมาแล้ว{}".format(
            doc.get("bom_no", ""),
            " พร้อมใบขอราคา {} ใบ".format(num_or(count)) if count else "",
        ),
    }


@router.delete(
    "/{bom_id}/purge",
    summary="ลบถาวรออกจากฐานข้อมูล (admin เท่านั้น)",
    description=(
        "ต้องอยู่ในถังขยะก่อน — กันการกดลบถาวรพลาดในครั้งเดียว · "
        "ลบใบขอราคา ผู้ถูกเชิญ ใบเสนอราคา และไฟล์แนบของโครงการนี้ทั้งหมดไปด้วย "
        "(รวมใบเสนอราคาที่ผู้ขายอัปโหลดมา) คืนจำนวนที่ลบไปให้ตรวจสอบ"
    ),
)
async def purge_bom(bom_id: str, user: Dict[str, Any] = Depends(require_admin)):
    doc = await _get_or_404(bom_id, user)
    if not doc.get("deleted_at"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ต้องย้ายเข้าถังขยะก่อนจึงลบถาวรได้ — กันการกดพลาดครั้งเดียวแล้วหายถาวร",
        )

    db = get_database()
    rfqs = await db[schema.RFQS].find({"bom_id": doc["_id"]}, {"_id": 1}).to_list(None)
    rfq_ids = [r["_id"] for r in rfqs]

    # ไล่ลบไฟล์ในฐานข้อมูลด้วย ไม่ใช่ลบแค่แถวที่อ้างถึงมัน
    # ไฟล์ที่ไม่มีใครอ้างถึงแล้วจะกินที่ไปเรื่อย ๆ และไม่มีหน้าจอไหนพาไปหามันได้อีก
    files_removed = 0
    if rfq_ids:
        invites = await db[schema.RFQ_INVITES].find(
            {"rfq_id": {"$in": rfq_ids}}, {"rfq_document": 1}).to_list(None)
        quotes = await db[schema.RFQ_QUOTES].find(
            {"rfq_id": {"$in": rfq_ids}}, {"attachments": 1}).to_list(None)
        file_ids = [(inv.get("rfq_document") or {}).get("file_id") for inv in invites]
        for quote in quotes:
            file_ids += [a.get("file_id") for a in (quote.get("attachments") or [])]
        for file_id in [f for f in file_ids if f]:
            if await filestore.delete(file_id):
                files_removed += 1

        await db[schema.RFQ_QUOTES].delete_many({"rfq_id": {"$in": rfq_ids}})
        await db[schema.RFQ_INVITES].delete_many({"rfq_id": {"$in": rfq_ids}})
        await db[schema.RFQS].delete_many({"_id": {"$in": rfq_ids}})

    await db[schema.BOMS].delete_one({"_id": doc["_id"]})
    return {
        "ok": True,
        "bom_no": doc.get("bom_no", ""),
        "rfqs_deleted": len(rfq_ids),
        "files_deleted": files_removed,
        "message": "ลบ {} ถาวรแล้ว พร้อมใบขอราคา {} ใบ และไฟล์แนบ {} ไฟล์".format(
            doc.get("bom_no", ""), num_or(len(rfq_ids)), num_or(files_removed)),
    }


@router.post(
    "/{bom_id}/assignees",
    summary="เพิ่ม/ถอดคนเข้าออกจากโครงการ",
    description=(
        "ใช้ตอนต้องให้คนนอกหน่วยงานเข้ามาช่วย · "
        "คนในหน่วยงานเดียวกันเห็นอยู่แล้วโดยไม่ต้อง assign"
    ),
)
async def set_assignees(
    bom_id: str, payload: BomAssignRequest, user: Dict[str, Any] = Depends(require_buyer)
):
    doc = await _get_or_404(bom_id, user)
    bom_access.require_manage(user, doc)

    current = list(doc.get("assignees") or [])
    unknown = []
    for email in payload.add:
        email = email.strip().lower()
        if not email:
            continue
        # ต้องมีบัญชีอยู่จริง ไม่งั้นพิมพ์อีเมลผิดแล้วนึกว่า assign สำเร็จ
        if not await user_service.get_by_email(email):
            unknown.append(email)
            continue
        if email not in current:
            current.append(email)
    for email in payload.remove:
        email = email.strip().lower()
        if email in current:
            current.remove(email)

    await get_database()[schema.BOMS].update_one(
        {"_id": doc["_id"]}, {"$set": {"assignees": current, "updated_at": utcnow()}}
    )
    if unknown and not current:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ไม่พบผู้ใช้: {} — ต้องมีบัญชีในระบบก่อนจึงเพิ่มเข้าโครงการได้".format(", ".join(unknown)),
        )
    return {"ok": True, "assignees": current, "unknown": unknown}


# ------------------------------------------------------------------ ราย บรรทัด
@router.get(
    "/{bom_id}/lines/{line_no}/candidates",
    summary="หาสินค้าที่ใกล้เคียงสำหรับบรรทัดนี้ (ใช้ตอนคลิกแก้รายตัว)",
    description="ไม่ใส่ q = ใช้ชื่อจาก BOM ค้นให้ · ใส่ q = ค้นด้วยคำที่พิมพ์เอง",
)
async def line_candidates(
    bom_id: str,
    line_no: int,
    q: str = Query("", description="คำค้นที่พิมพ์เอง"),
    limit: int = Query(8, ge=1, le=30),
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = await _get_or_404(bom_id, user)
    line = next((l for l in doc.get("lines", []) if l.get("line_no") == line_no), None)
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบบรรทัดนี้")
    text = q.strip() or line.get("name", "")
    return {
        "query": text,
        "from_bom": not q.strip(),
        "items": serialize(await bom_service.find_candidates(text, limit=limit)),
    }


@router.patch(
    "/{bom_id}/lines/{line_no}",
    summary="แก้บรรทัดเดียว — เปลี่ยนสินค้าที่จับคู่ / แก้จำนวน / กรอกราคาเอง",
)
async def patch_line(
    bom_id: str, line_no: int, payload: BomLinePatch,
    user: Dict[str, Any] = Depends(require_buyer),
):
    doc = await _get_or_404(bom_id, user)
    lines: List[Dict[str, Any]] = doc.get("lines") or []
    index = next((i for i, l in enumerate(lines) if l.get("line_no") == line_no), None)
    if index is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบบรรทัดนี้")

    line = dict(lines[index])
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        line["name"] = str(data["name"]).strip()[:300]
    if "qty" in data and data["qty"] is not None:
        line["qty"] = float(data["qty"])
    if "uom" in data and data["uom"] is not None:
        line["uom"] = str(data["uom"]).strip()[:20]
    if "remark" in data and data["remark"] is not None:
        line["remark"] = str(data["remark"]).strip()[:300]

    if "part_num" in data:
        part = (data["part_num"] or "").strip()
        if part:
            from app.services import epicor
            if not await epicor.get_item(part):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST, "ไม่พบรหัสสินค้า {} ในระบบ".format(part)
                )
            line["part_num"] = part
            line["match_source"] = "manual"
            line["match_score"] = 1.0     # คนเลือกเอง = ไม่ต้องเดาความมั่นใจอีก
        else:
            line["part_num"] = ""
            line["match_source"] = "none"
            line["match_score"] = 0.0

    if data.get("clear_manual_price"):
        line["manual_price"] = None
    elif "manual_price" in data and data["manual_price"] is not None:
        line["manual_price"] = float(data["manual_price"])

    lines[index] = line
    return await _save_and_view(doc["_id"], {"lines": lines}, user)


@router.post("/{bom_id}/lines", status_code=status.HTTP_201_CREATED, summary="เพิ่มบรรทัดใหม่")
async def add_line(
    bom_id: str, payload: BomLineIn, user: Dict[str, Any] = Depends(require_buyer)
):
    doc = await _get_or_404(bom_id, user)
    lines: List[Dict[str, Any]] = doc.get("lines") or []
    if len(lines) >= bom_service.MAX_LINES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "จำนวนรายการเต็มแล้ว")
    new_lines = await bom_service.match_lines([payload.model_dump()])
    new_lines[0]["line_no"] = max([l.get("line_no", 0) for l in lines] or [0]) + 1
    return await _save_and_view(doc["_id"], {"lines": lines + new_lines}, user)


@router.delete("/{bom_id}/lines/{line_no}", summary="ลบบรรทัด")
async def delete_line(
    bom_id: str, line_no: int, user: Dict[str, Any] = Depends(require_buyer)
):
    doc = await _get_or_404(bom_id, user)
    lines = [l for l in (doc.get("lines") or []) if l.get("line_no") != line_no]
    if len(lines) == len(doc.get("lines") or []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบบรรทัดนี้")
    return await _save_and_view(doc["_id"], {"lines": lines}, user)


@router.post(
    "/{bom_id}/rematch",
    summary="ให้ระบบจับคู่ใหม่ทั้งใบ",
    description="ข้ามบรรทัดที่คนเลือกเองไว้แล้ว เพื่อไม่ให้การกดปุ่มนี้ลบงานที่ทำมา",
)
async def rematch(bom_id: str, user: Dict[str, Any] = Depends(require_buyer)):
    doc = await _get_or_404(bom_id, user)
    lines: List[Dict[str, Any]] = []
    for line in doc.get("lines") or []:
        if line.get("match_source") in ("manual", "manual_price") or line.get("manual_price"):
            lines.append(line)
            continue
        rebuilt = await bom_service.match_lines([line])
        rebuilt[0]["line_no"] = line.get("line_no")
        rebuilt[0]["manual_price"] = line.get("manual_price")
        lines.append(rebuilt[0])
    return await _save_and_view(doc["_id"], {"lines": lines}, user)


# ------------------------------------------------------------------ ต่อยอด
@router.post("/{bom_id}/rfq", status_code=status.HTTP_201_CREATED, summary="ออกใบขอราคาจาก BOM นี้")
async def create_rfq_from_bom(
    bom_id: str, payload: BomRfqRequest, user: Dict[str, Any] = Depends(require_buyer)
):
    from app.api.routes.rfqs import create_rfq
    from app.models.rfq import RfqCreate, RfqLineIn

    doc = await _get_or_404(bom_id, user)
    lines = [l for l in (doc.get("lines") or []) if l.get("part_num")]
    if not lines:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ยังไม่มีบรรทัดไหนจับคู่กับสินค้าในระบบ จึงออกใบขอราคาไม่ได้",
        )

    # รวมรหัสซ้ำเป็นบรรทัดเดียว ไม่งั้นผู้ขายจะเห็นของเดิมสองแถว
    merged: Dict[str, Dict[str, Any]] = {}
    for line in lines:
        part = line["part_num"]
        if part in merged:
            merged[part]["qty"] += float(line.get("qty") or 0)
        else:
            merged[part] = {
                "part_num": part,
                "qty": float(line.get("qty") or 1),
                "uom": line.get("uom", ""),
                "remark": line.get("remark", "") or line.get("name", "")[:120],
            }

    rfq = await create_rfq(
        RfqCreate(
            title=(payload.title or "ขอราคาตาม {} · {}".format(
                doc.get("bom_no", ""), doc.get("title", "")))[:200],
            currency=doc.get("currency", "THB"),
            note="ออกจากงานประมาณราคา {}".format(doc.get("bom_no", "")),
            lines=[RfqLineIn(**row) for row in merged.values()],
            vendor_keys=payload.vendor_keys,
        ),
        user,
    )
    await _stamp_project(rfq, doc)
    await get_database()[schema.BOMS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"rfq_id": ObjectId(rfq["id"]), "rfq_no": rfq["rfq_no"],
                  "status": "rfq_sent", "updated_at": utcnow()}},
    )
    return {"rfq": rfq, "line_count": len(merged),
            "skipped_lines": len(doc.get("lines") or []) - len(lines)}


@router.get(
    "/{bom_id}/rfq-plan",
    summary="ดูว่าจะออกใบขอราคาแยกรายตัวได้กี่ใบ และมีผู้ขายรายไหนให้เลือกบ้าง",
    description=(
        "คืนรายการที่จับคู่แล้วทั้งหมด พร้อมผู้ขายที่เคยขายรหัสนั้นจริง "
        "แนบราคาล่าสุดของผู้ขายแต่ละรายและคะแนนความตรงเวลามาด้วย"
    ),
)
async def get_rfq_plan(
    bom_id: str,
    line_no: Optional[int] = Query(None, ge=1, description="ขอเฉพาะบรรทัดเดียว"),
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = await _get_or_404(bom_id, user)
    return serialize(await bom_service.rfq_plan(doc, line_no=line_no))


@router.get(
    "/{bom_id}/lines/{line_no}/vendor-search",
    summary="ค้นหาผู้ขายเพิ่ม — ตามชื่อผู้ขาย หรือตามอุปกรณ์ที่ใกล้เคียง",
    description=(
        "by=name  → ค้นจากชื่อ/รหัส/อีเมลของผู้ขาย · "
        "by=item  → ค้นสินค้าที่คล้ายกันก่อน แล้วคืนผู้ขายที่เคยขายของพวกนั้น "
        "พร้อมบอกว่ามาจากสินค้าตัวไหน (ไม่ใส่ q = ใช้ชื่อจาก BOM ค้นให้)"
    ),
)
async def vendor_search(
    bom_id: str,
    line_no: int,
    q: str = Query("", description="คำค้น"),
    by: str = Query("item", pattern="^(name|item)$"),
    limit: int = Query(12, ge=1, le=30),
    user: Dict[str, Any] = Depends(get_current_user),
):
    from app.services import delivery, epicor

    doc = await _get_or_404(bom_id, user)
    line = next((l for l in doc.get("lines", []) if l.get("line_no") == line_no), None)
    if not line:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบบรรทัดนี้")

    text = q.strip() or line.get("name", "")
    # ผลค้นต้องบอกด้วยว่าเจ้าไหนเชิญไปแล้ว ไม่งั้นคนกดเลือกซ้ำโดยไม่รู้ตัว
    invited = await bom_service.invited_vendors(line)

    if by == "name":
        if not q.strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "ค้นตามชื่อผู้ขายต้องระบุคำค้น")
        found = await epicor.search_vendors(q=text, limit=limit)
        await delivery.attach_scores(found["items"])
        bom_service.mark_invited(found["items"], invited)
        return serialize({"by": "name", "query": text, "items": found["items"],
                          "total": found["total"], "via_items": []})

    result = await bom_service.vendors_for_similar(text, limit=limit)
    bom_service.mark_invited(result["items"], invited)
    return serialize(dict(result, by="item"))


@router.post(
    "/{bom_id}/rfqs",
    status_code=status.HTTP_201_CREATED,
    summary="ออกใบขอราคาแยกใบต่อรายการ (1 รายการ = 1 ใบ) เลือกผู้ขายได้ต่อรายการ",
    description=(
        "ต่างจาก POST /boms/{id}/rfq ที่รวมทุกรายการไว้ในใบเดียว · "
        "แบบนี้เหมาะเมื่อผู้ขายแต่ละเจ้าขายคนละอย่าง จะได้ไม่ต้องส่งของที่เขาไม่ได้ขายไปให้"
    ),
)
async def create_rfqs_per_item(
    bom_id: str, payload: BomRfqPerItemRequest,
    user: Dict[str, Any] = Depends(require_buyer),
):
    from app.api.routes.rfqs import create_rfq, send_rfq
    from app.models.rfq import RfqCreate, RfqLineIn, RfqSendRequest
    from app.services import vendor_directory as vd

    db = get_database()
    doc = await _get_or_404(bom_id, user)
    lines = {l.get("line_no"): l for l in (doc.get("lines") or [])}

    if not payload.items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ยังไม่ได้เลือกรายการที่จะออกใบขอราคา")

    # ---- คัดรายการที่ออกใบได้จริงก่อน แล้วค่อยตัดสินใจว่าจะรวมใบยังไง
    usable: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for item in payload.items:
        line = lines.get(item.line_no)
        if not line:
            skipped.append({"line_no": item.line_no, "reason": "ไม่พบบรรทัดนี้"})
        elif not line.get("part_num"):
            skipped.append({"line_no": item.line_no, "name": line.get("name", ""),
                            "reason": "ยังไม่ได้จับคู่กับสินค้าในระบบ"})
        elif not item.vendor_keys:
            # ใบขอราคาที่ไม่มีผู้ขายสักราย = ใบที่ไม่มีใครตอบ ออกไปก็เปล่าประโยชน์
            skipped.append({"line_no": item.line_no, "name": line.get("name", ""),
                            "reason": "ยังไม่ได้เลือกผู้ขาย"})
        else:
            usable.append({"item": item, "line": line})

    # ---- กันออกใบซ้ำไปหาเจ้าที่เชิญไปแล้ว
    # ถามซ้ำมีเหตุผลอยู่จริง (ราคาเก่าหมดอายุ / เปลี่ยนรหัสที่จับคู่ใหม่) จึงไม่ห้ามตาย
    # แต่ต้องเป็นการตั้งใจกด ไม่ใช่ผลข้างเคียงของการกดออกใบรอบสอง
    # ค่าตั้งต้นจึงตัดเจ้าที่ซ้ำออกแล้วรายงานกลับไปว่าตัดใครออกเพราะอะไร
    repeated: List[Dict[str, Any]] = []
    kept: List[Dict[str, Any]] = []
    for row in usable:
        item, line = row["item"], row["line"]
        invited = await bom_service.invited_vendors(line)
        dup = [k for k in item.vendor_keys if k in invited]
        if dup and not payload.allow_repeat:
            repeated.extend(
                {"line_no": item.line_no, "vendor_key": k, "rfq_nos": invited[k]}
                for k in dup
            )
            fresh = [k for k in item.vendor_keys if k not in invited]
            if not fresh:
                skipped.append({
                    "line_no": item.line_no, "name": line.get("name", ""),
                    "reason": "ผู้ขายที่เลือกถูกเชิญให้เสนอราคารายการนี้ไปแล้วทั้งหมด ({})".format(
                        " · ".join(sorted({n for k in dup for n in invited[k] if n})) or "ใบก่อนหน้า"),
                })
                continue
            item.vendor_keys = fresh
        kept.append(row)
    usable = kept

    def rfq_line(line: Dict[str, Any]) -> "RfqLineIn":
        return RfqLineIn(
            part_num=line["part_num"],
            qty=float(line.get("qty") or 1),
            uom=line.get("uom", ""),
            remark=line.get("remark", "") or line.get("name", "")[:120],
        )

    def remember(line: Dict[str, Any], rfq: Dict[str, Any], vendor_key: str = "") -> None:
        """บรรทัดหนึ่งอาจอยู่ในใบของผู้ขายหลายเจ้า จึงเก็บเป็นรายการ ไม่ใช่ค่าเดียว"""
        rows = line.get("rfqs") or []
        if not any(str(r.get("rfq_id")) == rfq["id"] for r in rows):
            rows.append({"rfq_id": ObjectId(rfq["id"]), "rfq_no": rfq["rfq_no"],
                         "vendor_key": vendor_key})
        line["rfqs"] = rows
        line["rfq_id"] = ObjectId(rfq["id"])       # ใบล่าสุด — ใช้แสดงย่อ ๆ
        line["rfq_no"] = rfq["rfq_no"]

    async def issue(title: str, note: str, rfq_lines: List["RfqLineIn"],
                    vendor_keys: List[str]) -> Dict[str, Any]:
        rfq = await create_rfq(
            RfqCreate(title=title[:200], currency=doc.get("currency", "THB"),
                      note=note, lines=rfq_lines, vendor_keys=vendor_keys),
            user,
        )
        await _stamp_project(rfq, doc)
        if payload.send:
            result = await send_rfq(rfq["id"], RfqSendRequest(message=payload.message), user)
            rfq["_sent"] = result.get("sent", 0)
        return rfq

    created: List[Dict[str, Any]] = []

    if payload.group_by == "vendor":
        # ผู้ขายเจ้าเดียวที่ขายหลายรายการในโครงการนี้ ควรได้ใบเดียวที่มีของครบ
        # ไม่ใช่หลายใบใบละชิ้น — ฝั่งเขาตอบง่ายกว่า ฝั่งเราตามน้อยกว่า
        by_vendor: Dict[str, List[Dict[str, Any]]] = {}
        for row in usable:
            for key in row["item"].vendor_keys:
                by_vendor.setdefault(key, []).append(row["line"])

        vendors = await vd.get_many(set(by_vendor))
        for vendor_key, vendor_lines in by_vendor.items():
            name = (vendors.get(vendor_key) or {}).get("name", vendor_key)
            # BOM อาจมีของรหัสเดียวกันหลายบรรทัด — ในใบเดียวต้องรวมเป็นแถวเดียว
            # ไม่งั้นผู้ขายเห็นของซ้ำสองแถว และตอนประกาศผู้ชนะจะแยกไม่ออกว่าหมายถึงแถวไหน
            merged: Dict[str, "RfqLineIn"] = {}
            for line in vendor_lines:
                part = line["part_num"]
                if part in merged:
                    merged[part].qty += float(line.get("qty") or 0)
                else:
                    merged[part] = rfq_line(line)
            rfq = await issue(
                title="ขอราคา {} · {} ({} รายการ)".format(
                    doc.get("bom_no", ""), name, len(merged)),
                note=payload.note or "ออกจากงานประมาณราคา {}".format(doc.get("bom_no", "")),
                rfq_lines=list(merged.values()),
                vendor_keys=[vendor_key],
            )
            for line in vendor_lines:
                remember(line, rfq, vendor_key)
            created.append({
                "rfq_id": rfq["id"],
                "rfq_no": rfq["rfq_no"],
                "vendor_key": vendor_key,
                "vendor_name": name,
                "vendor_count": 1,
                "line_count": len(merged),
                "lines": [l.get("line_no") for l in vendor_lines],
                "name": name,
                "sent": rfq.get("_sent", 0),
            })
    else:
        for row in usable:
            item, line = row["item"], row["line"]
            rfq = await issue(
                title=item.title or "ขอราคา {} · {}".format(
                    line.get("part_num", ""), line.get("name", "")),
                note=payload.note or "ออกจากงานประมาณราคา {} รายการที่ {}".format(
                    doc.get("bom_no", ""), item.line_no),
                rfq_lines=[rfq_line(line)],
                vendor_keys=item.vendor_keys,
            )
            remember(line, rfq)
            created.append({
                "line_no": item.line_no,
                "name": line.get("name", ""),
                "part_num": line["part_num"],
                "rfq_id": rfq["id"],
                "rfq_no": rfq["rfq_no"],
                "vendor_count": len(item.vendor_keys),
                "line_count": 1,
                "lines": [item.line_no],
                "sent": rfq.get("_sent", 0),
            })

    if not created:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ออกใบขอราคาไม่ได้สักใบ — {}{}".format(
                skipped[0]["reason"] if skipped else "ไม่ทราบสาเหตุ",
                " · ถ้าตั้งใจขอราคาซ้ำจากเจ้าเดิม ให้ติ๊ก \"ขอซ้ำจากเจ้าที่เคยเชิญ\""
                if repeated else "",
            ),
        )

    changes: Dict[str, Any] = {"lines": list(lines.values()), "updated_at": utcnow()}
    if doc.get("status") in (None, "draft", "estimated"):
        changes["status"] = "rfq_sent"
    await db[schema.BOMS].update_one({"_id": doc["_id"]}, {"$set": changes})

    fresh = await db[schema.BOMS].find_one({"_id": doc["_id"]})
    view = await bom_service.build_view(fresh)
    await db[schema.BOMS].update_one(
        {"_id": doc["_id"]}, {"$set": {"totals": view["totals"], "progress": view["progress"]}}
    )
    return serialize({"created": created, "skipped": skipped, "repeated": repeated,
                      "group_by": payload.group_by, "bom": view})


@router.get(
    "/{bom_id}/comparison",
    summary="เทียบราคาทั้งโครงการ — มองเป็นรายสินค้า ไม่ใช่รายผู้ขาย",
    description=(
        "รวมราคาจากทุกใบขอราคาของโครงการนี้กลับมาเรียงเป็นแถวละสินค้า "
        "คอลัมน์เป็นผู้ขาย ไฮไลต์ราคาต่ำสุดของแต่ละแถว และเทียบกับงบที่ตั้งไว้"
    ),
)
async def bom_comparison(bom_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = await _get_or_404(bom_id, user)
    return serialize(await bom_service.comparison(doc))


@router.post(
    "/{bom_id}/award",
    summary="เลือกผู้ชนะรายสินค้า จากหน้าเทียบราคาของโครงการ",
    description=(
        "ส่งเป็นคู่ (รายการ, ผู้ขาย) ระบบจะไปประกาศผู้ชนะในใบขอราคาที่มีทั้งสองอย่างนั้นให้เอง — "
        "คนเลือกจากสินค้า ไม่ต้องจำว่าของชิ้นนี้อยู่ในใบไหน"
    ),
)
async def award_from_bom(
    bom_id: str, payload: BomAwardRequest, user: Dict[str, Any] = Depends(require_buyer)
):
    from app.api.routes.rfqs import award
    from app.models.rfq import AwardRequest

    doc = await _get_or_404(bom_id, user)
    lines = {l.get("line_no"): l for l in (doc.get("lines") or [])}
    if not payload.awards:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ยังไม่ได้เลือกผู้ชนะสักรายการ")

    # จับคู่ (รายการ, ผู้ขาย) → ใบขอราคาที่มีทั้งคู่ แล้วค่อยรวมยิงทีละใบ
    by_rfq: Dict[str, Dict[str, str]] = {}
    skipped: List[Dict[str, Any]] = []
    for item in payload.awards:
        line = lines.get(item.line_no)
        if not line or not line.get("part_num"):
            skipped.append({"line_no": item.line_no, "reason": "ไม่พบรายการ หรือยังไม่ได้จับคู่"})
            continue
        target = next(
            (r for r in (line.get("rfqs") or [])
             if not r.get("vendor_key") or r.get("vendor_key") == item.vendor_key),
            None,
        )
        if not target:
            skipped.append({"line_no": item.line_no,
                            "reason": "ผู้ขายรายนี้ไม่ได้อยู่ในใบขอราคาของรายการนี้"})
            continue
        by_rfq.setdefault(str(target["rfq_id"]), {})[str(line["part_num"])] = item.vendor_key

    if not by_rfq:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ประกาศผู้ชนะไม่ได้ — {}".format(skipped[0]["reason"] if skipped else "ไม่ทราบสาเหตุ"),
        )

    awarded = []
    for rfq_id, line_awards in by_rfq.items():
        result = await award(
            rfq_id, AwardRequest(line_awards=line_awards, reason=payload.reason), user
        )
        awarded.append({"rfq_id": rfq_id, "rfq_no": result.get("rfq_no", ""),
                        "lines": list(line_awards)})

    fresh = await get_database()[schema.BOMS].find_one({"_id": doc["_id"]})
    view = await bom_service.build_view(fresh)
    await get_database()[schema.BOMS].update_one(
        {"_id": doc["_id"]}, {"$set": {"totals": view["totals"], "progress": view["progress"]}}
    )
    return serialize({"awarded": awarded, "skipped": skipped, "bom": view})


@router.get("/{bom_id}/export", summary="โหลดงบประมาณเป็นไฟล์ Excel")
async def export_bom(bom_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = await _get_or_404(bom_id, user)
    view = await bom_service.build_view(doc)
    # งบเปลี่ยนทุกครั้งที่แก้ BOM จึงสร้างสดแล้วส่งกลับเลย ไม่เก็บไฟล์ค้างไว้ให้เก่า
    return filestore.response(build_bom_workbook(view))
