"""RFQ — ออกใบขอราคาจากรหัสสินค้าใน Epicor แล้วส่งให้ผู้ขายทีละหลายราย

การส่งทำสองอย่างพร้อมกัน:
1. ออก "ใบขอราคา" (Excel) หนึ่งใบต่อผู้ขายหนึ่งราย สำหรับแนบส่งไปด้วย
2. ออกลิงก์ portal พร้อม token ให้ผู้ขายกรอกราคาออนไลน์ และแนบใบเสนอราคาของตัวเองกลับมา

**สิ่งที่เปลี่ยนไปจากเดิม** — บรรทัดของ RFQ อ้างสินค้าด้วย ``part_num`` ของ Epicor
ไม่ใช่ ObjectId ของแคตตาล็อกที่ระบบสร้างเอง จึงไม่ต้อง "เพิ่มสินค้าเข้าระบบ" ก่อนออก RFQ
และทุกบรรทัดพก **ราคาล่าสุดที่เคยซื้อ** ไปด้วย เพื่อใช้เทียบตอนผู้ขายเสนอราคากลับมา
"""
import secrets
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from app.api.deps import get_current_user, require_admin, require_buyer
from app.core.config import settings
from app.db import schema
from app.db.mongodb import get_database
from app.models.common import paged, serialize, to_oid, utcnow
from app.models.rfq import (
    RfqBulkRequest,
    AwardRequest,
    CloseRequest,
    RfqCreate,
    RfqInviteIn,
    RfqSendRequest,
    RfqUpdate,
)
from app.services import delivery, epicor
from app.services import vendor_directory as vd
from app.services import bom_access, filestore
from app.services.rfq_doc import build_comparison_workbook, build_rfq_workbook

router = APIRouter(prefix="/rfqs", tags=["rfqs"])

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------- helpers
def to_dt(value: Any) -> Optional[datetime]:
    """MongoDB เก็บ date เปล่า ๆ ไม่ได้ ต้องแปลงเป็น datetime ก่อน"""
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    return value


async def _next_rfq_no() -> str:
    year = utcnow().year
    doc = await get_database()[schema.COUNTERS].find_one_and_update(
        {"_id": "rfq:{}".format(year)}, {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return "RFQ-{}-{:04d}".format(year, int(doc["seq"]))


async def _build_lines(raw_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """เก็บ snapshot ของสินค้า + ราคาอ้างอิงไว้ใน RFQ

    ราคาที่ผู้ขายเสนอกลับมาต้องเทียบกับ "สเปกและราคา ณ วันที่ออกใบ" ไม่ใช่ค่าที่เปลี่ยนทีหลัง
    """
    part_nums = [str(l.get("part_num") or "").strip() for l in raw_lines]
    if not all(part_nums):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ทุกบรรทัดต้องระบุรหัสสินค้า (part_num)")

    db = get_database()
    docs = await db[schema.EP_ITEMS].find(
        {"partNum": {"$in": part_nums}}, epicor.ITEM_FIELDS
    ).to_list(len(part_nums))
    by_part = {d["partNum"]: d for d in docs}
    prices = await epicor.prices_for(part_nums)

    missing = [p for p in part_nums if p not in by_part and p not in prices]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "ไม่พบรหัสสินค้าใน Epicor: {}".format(", ".join(sorted(set(missing)))),
        )

    lines = []
    for raw, part in zip(raw_lines, part_nums):
        doc = by_part.get(part) or {}
        price = prices.get(part) or {}
        last = price.get("last") or {}
        lowest = price.get("lowest") or {}
        description = doc.get("description") or price.get("description") or part

        lines.append({
            "part_num": part,
            "item_code": part,                      # ใช้ในไฟล์ Excel ใบขอราคา
            "name": description,
            "description": description,
            "manufacturer": "",
            "mpn": "",
            "category_code": doc.get("classId") or price.get("classId") or "",
            "specs": {},
            "qty": float(raw.get("qty") or 1),
            "uom": raw.get("uom") or doc.get("uom") or price.get("uom") or "EA",
            "target_price": raw.get("target_price"),
            "required_date": to_dt(raw.get("required_date")),
            "remark": raw.get("remark", ""),
            # ราคาอ้างอิงจากประวัติจริง — ไม่โชว์ให้ผู้ขายเห็น ใช้เฉพาะตอนเทียบราคาภายใน
            "last_price": last.get("unitCost"),
            "last_price_date": to_dt(last.get("date")),
            "last_price_vendor": last.get("vendorName", ""),
            "lowest_price": lowest.get("unitCost"),
            "lowest_price_vendor": lowest.get("vendorName", ""),
        })
    return lines


def _portal_url(token: str) -> str:
    return "{}/portal/{}".format(settings.FRONTEND_URL.rstrip("/"), token)


async def _invite_rows(rfq_id: ObjectId) -> List[Dict[str, Any]]:
    db = get_database()
    invites = await db[schema.RFQ_INVITES].find({"rfq_id": rfq_id}).to_list(500)
    quoted = set(await db[schema.RFQ_QUOTES].distinct("vendor_key", {"rfq_id": rfq_id}))
    rows = []
    for inv in invites:
        row = serialize(inv)
        row["portal_url"] = _portal_url(inv.get("token", ""))
        row["has_quote"] = inv["vendor_key"] in quoted
        row["rfq_document_url"] = "/api/rfqs/{}/document/{}".format(rfq_id, inv["vendor_key"])
        rows.append(row)
    rows.sort(key=lambda r: r.get("vendor_name", ""))
    return rows


async def _get_rfq_or_404(rfq_id: str, user: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    doc = await get_database()[schema.RFQS].find_one({"_id": to_oid(rfq_id, "rfq_id")})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ RFQ")
    if doc.get("deleted_at"):
        # ถูกยกเลิกพร้อมโครงการ — บอกตรง ๆ ว่ายกเลิก ไม่ใช่ "ไม่พบ" เฉย ๆ
        # ไม่งั้นคนกดลิงก์เก่าจะนึกว่าระบบพัง แล้วไปออกใบใหม่ซ้ำ
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "ใบขอราคา {} ถูกยกเลิกพร้อมโครงการ{} — กู้โครงการกลับมาจากถังขยะแล้วใบนี้จะกลับมาด้วย".format(
                doc.get("rfq_no", ""),
                " " + doc["bom_no"] if doc.get("bom_no") else "",
            ),
        )
    # ใบที่ออกจากโครงการต้องถูกจำกัดเหมือนโครงการ ไม่งั้นชื่อโครงการและราคา
    # จะรั่วผ่านหน้าใบขอราคาให้คนที่ไม่มีสิทธิ์เห็นโครงการนั้น
    if user is not None and doc.get("bom_id"):
        bom = await get_database()[schema.BOMS].find_one({"_id": doc["bom_id"]})
        if bom:
            bom_access.require_view(user, bom)
    return doc


async def _require_manage_rfq(user: Dict[str, Any], rfq: Dict[str, Any]) -> None:
    """ใครยกเลิกใบขอราคาใบนี้ได้

    ใบที่ออกจากโครงการ = เจ้าของโครงการหรือ admin (คนในหน่วยงานทำงานต่อได้ แต่ไม่ควรยกเลิกงานคนอื่น)
    ใบที่ขอราคาตรงจากหน้าสินค้า = คนที่ออกใบเอง หรือ admin
    """
    if bom_access.is_admin(user):
        return
    if rfq.get("bom_id"):
        bom = await get_database()[schema.BOMS].find_one({"_id": rfq["bom_id"]})
        if bom and bom_access.can_manage(user, bom):
            return
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "ใบนี้ออกจากโครงการ {} — ยกเลิกได้เฉพาะเจ้าของโครงการหรือผู้ดูแลระบบ".format(
                rfq.get("bom_no", "")),
        )
    if rfq.get("created_by") == user.get("email", ""):
        return
    raise HTTPException(
        status.HTTP_403_FORBIDDEN,
        "ยกเลิกได้เฉพาะคนที่ออกใบนี้ ({}) หรือผู้ดูแลระบบ".format(rfq.get("created_by", "")),
    )


async def _cancel_one(rfq: Dict[str, Any], user: Dict[str, Any]) -> int:
    """ยกเลิกใบเดียว คืนจำนวนลิงก์ที่ถูกตัด — ใช้ร่วมกันทั้งยกเลิกทีละใบและยกเลิกหลายใบ"""
    db = get_database()
    now = utcnow()
    await db[schema.RFQS].update_one(
        {"_id": rfq["_id"]},
        # deleted_with_bom=False → การกู้โครงการจะไม่ลากใบนี้กลับมาด้วย
        # เพราะคนตั้งใจยกเลิกใบนี้เอง ไม่ใช่หายไปเพราะโครงการถูกลบ
        {"$set": {"deleted_at": now, "deleted_by": user.get("email", ""),
                  "deleted_with_bom": False, "status": "cancelled", "updated_at": now}},
    )
    return await db[schema.RFQ_INVITES].count_documents({"rfq_id": rfq["_id"]})


@router.post(
    "/bulk-cancel",
    summary="ยกเลิกใบขอราคาหลายใบที่ติ๊กเลือกไว้",
    description=(
        "ทำทีละใบเหมือนกดยกเลิกเอง — ใบที่ไม่มีสิทธิ์หรือยกเลิกอยู่แล้วจะถูกข้าม "
        "แล้วรายงานกลับมาว่าข้ามใบไหนเพราะอะไร ไม่ล้มทั้งชุดและไม่ข้ามแบบเงียบ ๆ"
    ),
)
async def bulk_cancel(payload: RfqBulkRequest, user: Dict[str, Any] = Depends(require_buyer)):
    cancelled: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    links = 0

    for rfq_id in payload.rfq_ids:
        try:
            rfq = await _get_rfq_or_404(rfq_id, user)
            await _require_manage_rfq(user, rfq)
        except HTTPException as exc:
            skipped.append({"rfq_id": rfq_id, "reason": str(exc.detail)})
            continue
        count = await _cancel_one(rfq, user)
        links += count
        cancelled.append({"rfq_id": rfq_id, "rfq_no": rfq.get("rfq_no", ""),
                          "links_revoked": count})

    if not cancelled:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ยกเลิกไม่ได้สักใบ — {}".format(skipped[0]["reason"] if skipped else "ไม่ทราบสาเหตุ"),
        )
    return {
        "ok": True,
        "cancelled": cancelled,
        "skipped": skipped,
        "links_revoked": links,
        "message": "ยกเลิก {} ใบแล้ว — ลิงก์ของผู้ขาย {} รายใช้ไม่ได้อีก{}".format(
            len(cancelled), links,
            " · ข้าม {} ใบ".format(len(skipped)) if skipped else "",
        ),
    }


@router.post("/bulk-restore", summary="กู้ใบขอราคาหลายใบที่ติ๊กเลือกไว้")
async def bulk_restore(payload: RfqBulkRequest, user: Dict[str, Any] = Depends(require_buyer)):
    restored: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for rfq_id in payload.rfq_ids:
        try:
            res = await restore_rfq(rfq_id, user)
            restored.append({"rfq_id": rfq_id, "rfq_no": res.get("rfq_no", "")})
        except HTTPException as exc:
            skipped.append({"rfq_id": rfq_id, "reason": str(exc.detail)})

    if not restored:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "กู้ไม่ได้สักใบ — {}".format(skipped[0]["reason"] if skipped else "ไม่ทราบสาเหตุ"),
        )
    return {
        "ok": True, "restored": restored, "skipped": skipped,
        "message": "กู้กลับมา {} ใบ ลิงก์ของผู้ขายใช้ได้อีกครั้ง{}".format(
            len(restored), " · ข้าม {} ใบ".format(len(skipped)) if skipped else ""),
    }


@router.delete(
    "/{rfq_id}",
    summary="ยกเลิกใบขอราคา (เพิกถอนลิงก์ของผู้ขายทันที)",
    description=(
        "ไม่ได้ลบออกจากฐานข้อมูล แต่ซ่อนจากรายการและ **ตัดลิงก์ของผู้ขายทุกรายทันที** · "
        "ผู้ขายที่เปิดลิงก์เดิมจะเห็นว่า \"ใบขอราคานี้ถูกยกเลิกแล้ว\" และส่งราคาเข้ามาไม่ได้ · "
        "กู้คืนได้ที่ GET /rfqs?trash=true"
    ),
)
async def cancel_rfq(rfq_id: str, user: Dict[str, Any] = Depends(require_buyer)):
    rfq = await _get_rfq_or_404(rfq_id, user)
    await _require_manage_rfq(user, rfq)
    revoked = await _cancel_one(rfq, user)
    return {
        "ok": True,
        "rfq_no": rfq.get("rfq_no", ""),
        "links_revoked": revoked,
        "message": "ยกเลิก {} แล้ว — ลิงก์ของผู้ขาย {} รายใช้ไม่ได้อีก และจะขึ้นว่าใบนี้ถูกยกเลิก".format(
            rfq.get("rfq_no", ""), revoked),
    }


@router.post("/{rfq_id}/restore", summary="กู้ใบขอราคาที่ยกเลิกไว้กลับมา")
async def restore_rfq(rfq_id: str, user: Dict[str, Any] = Depends(require_buyer)):
    db = get_database()
    doc = await db[schema.RFQS].find_one({"_id": to_oid(rfq_id, "rfq_id")})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ RFQ")
    if not doc.get("deleted_at"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ใบนี้ไม่ได้ถูกยกเลิกไว้")
    await _require_manage_rfq(user, doc)

    if doc.get("bom_id"):
        # โครงการยังอยู่ในถังขยะ กู้ใบเดี่ยวขึ้นมาก็ไม่มีที่ยืน และจะเห็นในรายการ
        # ทั้งที่โครงการไม่มี — ต้องกู้โครงการก่อน
        bom = await db[schema.BOMS].find_one({"_id": doc["bom_id"]})
        if bom and bom.get("deleted_at"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "โครงการ {} ยังอยู่ในถังขยะ — กู้โครงการก่อน แล้วใบนี้จะกลับมาพร้อมกัน".format(
                    bom.get("bom_no", "")),
            )

    # ส่งออกไปแล้วให้กลับเป็น sent ถ้ายังไม่เคยส่งก็กลับเป็น draft
    back = "sent" if doc.get("sent_at") else "draft"
    await db[schema.RFQS].update_one(
        {"_id": doc["_id"]},
        {"$set": {"deleted_at": None, "deleted_by": "", "status": back, "updated_at": utcnow()}},
    )
    return {"ok": True, "rfq_no": doc.get("rfq_no", ""), "status": back,
            "message": "กู้ {} กลับมาแล้ว ลิงก์ของผู้ขายใช้ได้อีกครั้ง".format(doc.get("rfq_no", ""))}


async def _add_invites(
    rfq_id: ObjectId, vendor_keys: List[str], email_override: Dict[str, str]
) -> List[Dict[str, Any]]:
    db = get_database()
    canonical = {k: vd.make_key(vd.parse_key(k)[1]) for k in vendor_keys}
    vendors = await vd.get_many(canonical.values())
    missing = [k for k, c in canonical.items() if c not in vendors]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "ไม่พบผู้ขาย: {}".format(", ".join(missing))
        )

    for original, key in canonical.items():
        vendor = vendors[key]
        contacts = vendor.get("contacts") or []
        primary = next((c for c in contacts if c.get("is_primary")), contacts[0] if contacts else {})
        email = email_override.get(original) or email_override.get(key) \
            or primary.get("email") or vd.primary_email(vendor)
        await db[schema.RFQ_INVITES].update_one(
            {"rfq_id": rfq_id, "vendor_key": key},
            {
                "$setOnInsert": {
                    "token": secrets.token_urlsafe(32),
                    "status": "pending",
                    "created_at": utcnow(),
                    "sent_at": None, "viewed_at": None, "responded_at": None,
                    "rfq_document": None,
                },
                "$set": {
                    "source": vendor.get("source", vd.SOURCE),
                    "vendor_id": vendor["vendor_id"],
                    "vendor_name": vendor["name"],
                    "contact_email": email,
                    "contact_name": primary.get("name", ""),
                    "all_emails": vendor.get("emails", []),
                },
            },
            upsert=True,
        )
    return await _invite_rows(rfq_id)


# ==================================================================== create
@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="สร้าง RFQ",
    description="ระบุรหัสสินค้าของ Epicor ได้เลย ไม่ต้องเพิ่มเข้าแคตตาล็อกก่อน",
)
async def create_rfq(payload: RfqCreate, user: Dict[str, Any] = Depends(require_buyer)):
    db = get_database()
    if not payload.lines:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ต้องมีรายการสินค้าอย่างน้อย 1 รายการ")

    lines = await _build_lines([l.model_dump() for l in payload.lines])
    doc = {
        "rfq_no": await _next_rfq_no(),
        "title": payload.title,
        "status": "draft",
        "due_date": to_dt(payload.due_date),
        "currency": payload.currency,
        "incoterm": payload.incoterm,
        "payment_terms": payload.payment_terms,
        "delivery_place": payload.delivery_place,
        "note": payload.note,
        "lines": lines,
        "created_at": utcnow(),
        "created_by": user["email"],
        "sent_at": None,
    }
    res = await db[schema.RFQS].insert_one(doc)
    doc["_id"] = res.inserted_id

    if payload.vendor_keys:
        await _add_invites(res.inserted_id, payload.vendor_keys, {})

    out = serialize(doc)
    out["invites"] = await _invite_rows(res.inserted_id)
    return out


# ==================================================================== read
@router.get("", summary="รายการ RFQ")
async def list_rfqs(
    q: Optional[str] = None,
    rfq_status: Optional[str] = Query(None, alias="status"),
    trash: bool = Query(False, description="ดูใบที่ยกเลิกไว้ แทนรายการปกติ"),
    skip: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
    user: Dict[str, Any] = Depends(get_current_user),
):
    db = get_database()
    query: Dict[str, Any] = {}
    # ใบที่ไม่ได้ออกจากโครงการ (ขอราคาจากหน้าสินค้าตรง ๆ) ทุกคนยังเห็นได้เหมือนเดิม
    # ใบที่ถูกยกเลิก ไม่ต้องโผล่ในรายการปกติ — ดูได้ที่โหมดถังขยะ
    query["deleted_at"] = {"$ne": None} if trash else None
    visible = await bom_access.visible_bom_ids(user)
    if visible is not None:
        query["$and"] = [{"$or": [{"bom_id": None}, {"bom_id": {"$exists": False}},
                                  {"bom_id": {"$in": visible}}]}]
    if rfq_status:
        query["status"] = rfq_status
    if q:
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"rfq_no": rx}, {"title": rx}]

    total = await db[schema.RFQS].count_documents(query)
    docs = await db[schema.RFQS].find(query, {"lines": 0}).sort("created_at", -1) \
        .skip(skip).limit(limit).to_list(limit)

    ids = [d["_id"] for d in docs]
    invite_counts: Dict[Any, int] = {}
    quote_counts: Dict[Any, int] = {}
    for inv in await db[schema.RFQ_INVITES].find({"rfq_id": {"$in": ids}}, {"rfq_id": 1}).to_list(5000):
        invite_counts[inv["rfq_id"]] = invite_counts.get(inv["rfq_id"], 0) + 1
    for qt in await db[schema.RFQ_QUOTES].find({"rfq_id": {"$in": ids}}, {"rfq_id": 1}).to_list(5000):
        quote_counts[qt["rfq_id"]] = quote_counts.get(qt["rfq_id"], 0) + 1

    items = []
    for d in docs:
        row = serialize(d)
        row["vendor_count"] = invite_counts.get(d["_id"], 0)
        row["quote_count"] = quote_counts.get(d["_id"], 0)
        items.append(row)
    return paged(items, total, skip, limit)


@router.get("/{rfq_id}", summary="รายละเอียด RFQ พร้อมรายชื่อผู้ขายที่เชิญ")
async def get_rfq(rfq_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = await _get_rfq_or_404(rfq_id, user)
    invites = await _invite_rows(doc["_id"])
    out = serialize(doc)
    out["invites"] = invites
    out["vendor_count"] = len(invites)
    out["quote_count"] = sum(1 for i in invites if i["has_quote"])
    return out


@router.get(
    "/{rfq_id}/suggested-vendors",
    summary="ผู้ขายที่ควรขอราคา",
    description="ผู้ขายที่ Epicor บันทึกไว้ว่าเคยขายรหัสสินค้าเหล่านี้ให้เรา เรียงตามความครอบคลุม",
)
async def suggested_vendors(
    rfq_id: str,
    limit: int = Query(40, ge=1, le=200),
    user: Dict[str, Any] = Depends(get_current_user),
):
    doc = await _get_rfq_or_404(rfq_id, user)
    lines = doc.get("lines", [])
    if not lines:
        return {"total_items": 0, "vendors": []}

    part_nums = [str(l.get("part_num") or "") for l in lines]
    vendors = await vd.suggest_for_parts(part_nums, limit=limit)
    await delivery.attach_scores(vendors)
    invited = {i["vendor_key"] for i in await _invite_rows(doc["_id"])}
    for v in vendors:
        v["already_invited"] = v["vendor_key"] in invited
    return serialize({"total_items": len(lines), "vendors": vendors})


# ==================================================================== update
@router.patch("/{rfq_id}", summary="แก้ไข RFQ")
async def update_rfq(rfq_id: str, payload: RfqUpdate, user: Dict[str, Any] = Depends(require_buyer)):
    doc = await _get_rfq_or_404(rfq_id, user)
    if doc.get("status") not in ("draft", "sent"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "RFQ สถานะ {} แก้ไขไม่ได้แล้ว".format(doc.get("status"))
        )

    changes = payload.model_dump(exclude_unset=True)
    if changes.get("lines") is not None:
        if doc.get("status") == "sent":
            raise HTTPException(
                status.HTTP_409_CONFLICT, "RFQ ส่งออกไปแล้ว จึงแก้ไขรายการสินค้าไม่ได้"
            )
        changes["lines"] = await _build_lines(changes["lines"])
    if "due_date" in changes:
        changes["due_date"] = to_dt(changes["due_date"])
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่มีข้อมูลที่จะแก้ไข")

    changes["updated_at"] = utcnow()
    updated = await get_database()[schema.RFQS].find_one_and_update(
        {"_id": doc["_id"]}, {"$set": changes}, return_document=ReturnDocument.AFTER
    )
    return serialize(updated)


@router.post("/{rfq_id}/vendors", summary="เพิ่มผู้ขายเข้า RFQ")
async def add_vendors(
    rfq_id: str, payload: RfqInviteIn, user: Dict[str, Any] = Depends(require_buyer)
):
    doc = await _get_rfq_or_404(rfq_id, user)
    return await _add_invites(doc["_id"], payload.vendor_keys, dict(payload.contact_email_override))


@router.delete("/{rfq_id}/vendors/{vendor_key:path}", summary="ถอดผู้ขายออกจาก RFQ")
async def remove_vendor(
    rfq_id: str, vendor_key: str, user: Dict[str, Any] = Depends(require_buyer)
):
    db = get_database()
    rfq_oid = to_oid(rfq_id, "rfq_id")
    key = vd.make_key(vd.parse_key(vendor_key)[1])
    if await db[schema.RFQ_QUOTES].find_one({"rfq_id": rfq_oid, "vendor_key": key}):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "ผู้ขายรายนี้เสนอราคามาแล้ว จึงถอดออกจาก RFQ ไม่ได้"
        )
    res = await db[schema.RFQ_INVITES].delete_one({"rfq_id": rfq_oid, "vendor_key": key})
    if not res.deleted_count:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ขายรายนี้ใน RFQ")
    return {"ok": True}


@router.get("/{rfq_id}/invites", summary="รายชื่อผู้ขายที่เชิญ พร้อมลิงก์ portal")
async def list_invites(rfq_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    doc = await _get_rfq_or_404(rfq_id, user)
    return await _invite_rows(doc["_id"])


# ==================================================================== send
@router.post(
    "/{rfq_id}/send",
    summary="ออกใบขอราคาให้ผู้ขายทุกราย",
    description="สร้างไฟล์ Excel ใบขอราคาต่อผู้ขายหนึ่งราย + ลิงก์กรอกราคาออนไลน์",
)
async def send_rfq(
    rfq_id: str, payload: RfqSendRequest, user: Dict[str, Any] = Depends(require_buyer)
):
    db = get_database()
    rfq = await _get_rfq_or_404(rfq_id, user)
    if not rfq.get("lines"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "RFQ ไม่มีรายการสินค้า")

    query: Dict[str, Any] = {"rfq_id": rfq["_id"]}
    if payload.vendor_keys:
        query["vendor_key"] = {"$in": [vd.make_key(vd.parse_key(k)[1]) for k in payload.vendor_keys]}
    invites = await db[schema.RFQ_INVITES].find(query).to_list(500)
    if not invites:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ยังไม่ได้เลือกผู้ขายสำหรับ RFQ นี้")

    vendors = await vd.get_many(i["vendor_key"] for i in invites)
    rfq_view = serialize(rfq)
    missing_email = []

    for invite in invites:
        vendor = vendors.get(invite["vendor_key"], {})
        invite_view = serialize(invite)
        invite_view["portal_url"] = _portal_url(invite["token"])
        built = build_rfq_workbook(rfq_view, vendor, invite_view, payload.message)
        # ส่งซ้ำ = ออกไฟล์ใหม่ทับของเดิม ไม่เก็บสะสมไว้ทุกครั้งที่กดส่ง
        document = await filestore.replace(
            (invite.get("rfq_document") or {}).get("file_id"),
            built["data"], filename=built["filename"], content_type=built["content_type"],
            kind="rfq_doc", ref=rfq.get("rfq_no", ""),
        )
        if not invite.get("contact_email"):
            missing_email.append(invite.get("vendor_name") or invite["vendor_key"])

        new_status = "sent" if invite.get("status") in (None, "pending") else invite["status"]
        await db[schema.RFQ_INVITES].update_one(
            {"_id": invite["_id"]},
            {"$set": {
                "status": new_status, "sent_at": utcnow(),
                "message": payload.message, "rfq_document": document,
            }},
        )

    await db[schema.RFQS].update_one(
        {"_id": rfq["_id"]},
        {"$set": {"status": "sent", "sent_at": utcnow(), "sent_by": user["email"]}},
    )

    return {
        "rfq_no": rfq["rfq_no"],
        "sent": len(invites),
        "invites": await _invite_rows(rfq["_id"]),
        "email_delivery": "manual",
        "note": (
            "ระบบออกใบขอราคาและลิงก์กรอกราคาให้ผู้ขายครบทุกรายแล้ว "
            "คัดลอก portal_url ส่งให้ผู้ขายทางอีเมลของท่าน หรือดาวน์โหลดไฟล์ RFQ ไปแนบ"
        ),
        "vendors_without_email": missing_email,
    }


@router.get("/{rfq_id}/document/{vendor_key:path}", summary="ดาวน์โหลดใบขอราคาของผู้ขายรายนั้น")
async def download_rfq_document(
    rfq_id: str, vendor_key: str, user: Dict[str, Any] = Depends(get_current_user)
):
    db = get_database()
    rfq = await _get_rfq_or_404(rfq_id, user)
    key = vd.make_key(vd.parse_key(vendor_key)[1])
    invite = await db[schema.RFQ_INVITES].find_one({"rfq_id": rfq["_id"], "vendor_key": key})
    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ขายรายนี้ใน RFQ")

    document = invite.get("rfq_document")
    # ไฟล์นี้สร้างใหม่ได้เสมอจากข้อมูลใน RFQ — ถ้าหาไม่เจอก็สร้างให้ใหม่ ไม่ต้องแจ้ง error
    if not document or not document.get("file_id") or not await filestore.stat(document["file_id"]):
        vendor = await vd.get_one(key)
        invite_view = serialize(invite)
        invite_view["portal_url"] = _portal_url(invite["token"])
        built = build_rfq_workbook(serialize(rfq), vendor, invite_view, invite.get("message", ""))
        document = await filestore.put(
            built["data"], filename=built["filename"], content_type=built["content_type"],
            kind="rfq_doc", ref=rfq.get("rfq_no", ""),
        )
        await db[schema.RFQ_INVITES].update_one(
            {"_id": invite["_id"]}, {"$set": {"rfq_document": document}}
        )

    return filestore.response(await filestore.read(document["file_id"]))


# ==================================================================== quotes
@router.get("/{rfq_id}/quotes", summary="ใบเสนอราคาที่ได้รับ")
async def list_quotes(rfq_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    rfq = await _get_rfq_or_404(rfq_id, user)
    quotes = await get_database()[schema.RFQ_QUOTES].find(
        {"rfq_id": rfq["_id"]}
    ).sort("total", 1).to_list(500)
    return serialize(quotes)


async def _build_comparison(rfq: Dict[str, Any]) -> Dict[str, Any]:
    db = get_database()
    invites = await db[schema.RFQ_INVITES].find({"rfq_id": rfq["_id"]}).to_list(500)
    quotes = await db[schema.RFQ_QUOTES].find({"rfq_id": rfq["_id"]}).to_list(500)
    quote_by_vendor = {q["vendor_key"]: q for q in quotes}

    vendors = []
    for inv in sorted(invites, key=lambda i: i.get("vendor_name", "")):
        q = quote_by_vendor.get(inv["vendor_key"]) or {}
        vendors.append({
            "vendor_key": inv["vendor_key"],
            "vendor_id": inv.get("vendor_id", ""),
            "vendor_name": inv.get("vendor_name", ""),
            "source": inv.get("source", ""),
            "status": inv.get("status", "pending"),
            "currency": q.get("currency", rfq.get("currency", "THB")),
            "total": q.get("total"),
            "quoted_lines": len([l for l in q.get("lines", []) if not l.get("no_quote")]),
            "delivery_days": q.get("delivery_days"),
            "payment_terms": q.get("payment_terms", ""),
            "attachment_count": len(q.get("attachments", [])),
            # ให้ลิงก์โหลดจริงมาด้วย ไม่ใช่บอกแค่จำนวน — ก่อนหน้านี้ฝั่งผู้ซื้อเห็นว่า
            # "มีไฟล์แนบ 2 ไฟล์" แต่ไม่มีทางเปิดดูจากหน้าจอเลย
            "attachments": [
                {"file_id": str(a.get("file_id", "")), "filename": a.get("filename", ""),
                 "size": a.get("size", 0),
                 "url": "/api/files/{}".format(a.get("file_id", ""))}
                for a in q.get("attachments", []) if a.get("file_id")
            ],
            "submitted_at": q.get("submitted_at"),
        })

    rows = []
    for line in rfq.get("lines", []):
        part_num = str(line.get("part_num") or "")
        qty = float(line.get("qty") or 0)
        cells = []
        for inv in invites:
            q = quote_by_vendor.get(inv["vendor_key"])
            ql = None
            if q:
                ql = next(
                    (l for l in q.get("lines", []) if str(l.get("part_num")) == part_num), None
                )
            unit = None if not ql or ql.get("no_quote") else ql.get("unit_price")
            cells.append({
                "vendor_key": inv["vendor_key"],
                "unit_price": unit,
                "amount": round(unit * qty, 2) if unit is not None else None,
                "lead_time_days": (ql or {}).get("lead_time_days"),
                "moq": (ql or {}).get("moq"),
                "is_alternative": bool((ql or {}).get("is_alternative")),
                "no_quote": bool((ql or {}).get("no_quote")) if ql else q is not None,
                "is_lowest": False,
                "remark": (ql or {}).get("remark", ""),
            })

        priced = [c for c in cells if c["amount"] is not None]
        lowest = min(priced, key=lambda c: c["amount"]) if priced else None
        if lowest:
            for c in cells:
                if c["amount"] == lowest["amount"]:
                    c["is_lowest"] = True

        last_price = line.get("last_price")
        best_unit = min([c["unit_price"] for c in cells if c["unit_price"] is not None], default=None)
        rows.append({
            "part_num": part_num,
            "item_code": line.get("item_code", part_num),
            "name": line.get("name", ""),
            "qty": qty,
            "uom": line.get("uom", ""),
            "target_price": line.get("target_price"),
            # ราคาอ้างอิงจากประวัติซื้อจริง — ทำให้เห็นทันทีว่าเสนอมาถูกหรือแพงกว่าที่เคยซื้อ
            "last_price": last_price,
            "last_price_date": line.get("last_price_date"),
            "last_price_vendor": line.get("last_price_vendor", ""),
            "lowest_price": line.get("lowest_price"),
            "best_vs_last_pct": (
                round((best_unit - last_price) / last_price * 100, 2)
                if best_unit is not None and last_price else None
            ),
            "cells": cells,
            "lowest_vendor_key": lowest["vendor_key"] if lowest else None,
            "lowest_amount": lowest["amount"] if lowest else None,
        })

    # ถูกที่สุดไม่ได้แปลว่าดีที่สุดเสมอ — แนบประวัติการส่งตรงเวลาให้ตัดสินใจพร้อมกัน
    await delivery.attach_scores(vendors)

    totals = [(v["vendor_key"], v["total"]) for v in vendors if v["total"] is not None]
    best_total = min(totals, key=lambda t: t[1])[0] if totals else None
    split_total = sum(r["lowest_amount"] for r in rows if r["lowest_amount"] is not None)
    single_total = min([t[1] for t in totals]) if totals else None
    baseline = sum(
        (r["last_price"] or 0) * r["qty"] for r in rows if r["last_price"] is not None
    )

    return {
        "rfq_id": str(rfq["_id"]),
        "rfq_no": rfq.get("rfq_no", ""),
        "title": rfq.get("title", ""),
        "currency": rfq.get("currency", "THB"),
        "vendors": vendors,
        "rows": rows,
        "best_total_vendor_key": best_total,
        # ประหยัดได้เท่าไรถ้าแยกซื้อรายการละเจ้าที่ถูกที่สุด แทนที่จะซื้อจากเจ้าเดียว
        "split_award_total": round(split_total, 2) if rows else None,
        "single_vendor_total": single_total,
        "split_saving": (
            round(single_total - split_total, 2)
            if single_total is not None and split_total else None
        ),
        # เทียบกับ "ถ้าซื้อที่ราคาเดิม" — ตัวเลขที่ฝ่ายจัดซื้อใช้รายงานผลต่อรอง
        "baseline_total": round(baseline, 2) if baseline else None,
        "saving_vs_last_price": (
            round(baseline - split_total, 2) if baseline and split_total else None
        ),
    }


@router.get("/{rfq_id}/comparison", summary="ตารางเปรียบเทียบราคา (มีราคาเดิมให้เทียบด้วย)")
async def comparison(rfq_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """แถว = สินค้า, คอลัมน์ = ผู้ขาย, ไฮไลต์ราคาต่ำสุดของแต่ละแถว"""
    rfq = await _get_rfq_or_404(rfq_id, user)
    return serialize(await _build_comparison(rfq))


@router.get("/{rfq_id}/comparison.xlsx", summary="ดาวน์โหลดตารางเปรียบเทียบเป็น Excel")
async def comparison_xlsx(rfq_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    rfq = await _get_rfq_or_404(rfq_id, user)
    built = build_comparison_workbook(serialize(await _build_comparison(rfq)))
    # ตารางเทียบราคาเปลี่ยนทุกครั้งที่มีใบเสนอราคาเข้ามาใหม่ จึงสร้างสด ๆ ทุกครั้ง
    # และส่งกลับไปเลยโดยไม่เก็บ — เก็บไว้ก็มีแต่จะเก่าและทำให้คนโหลดของเก่าไปใช้
    return filestore.response(built)


# ==================================================================== close
@router.post("/{rfq_id}/award", summary="ประกาศผู้ชนะ (ทั้งใบ หรือแยกรายบรรทัด)")
async def award(rfq_id: str, payload: AwardRequest, user: Dict[str, Any] = Depends(require_buyer)):
    db = get_database()
    rfq = await _get_rfq_or_404(rfq_id, user)
    if not payload.vendor_key and not payload.line_awards:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ต้องระบุผู้ชนะทั้งใบ หรือแยกรายบรรทัด")

    awards: Dict[str, str] = {}
    if payload.vendor_key:
        winner = vd.make_key(vd.parse_key(payload.vendor_key)[1])
        awards = {str(l["part_num"]): winner for l in rfq.get("lines", [])}
    for part_num, key in payload.line_awards.items():
        awards[part_num] = vd.make_key(vd.parse_key(key)[1])

    vendors = await vd.get_many(set(awards.values()))
    missing = [k for k in set(awards.values()) if k not in vendors]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "ไม่พบผู้ขาย: {}".format(", ".join(missing))
        )

    quotes = {
        q["vendor_key"]: q
        for q in await db[schema.RFQ_QUOTES].find({"rfq_id": rfq["_id"]}).to_list(500)
    }
    # เก็บ OTD ณ วันที่ตัดสินไว้ด้วย เพื่อให้ย้อนดูได้ว่าตอนนั้นรู้อะไรบ้าง
    otd_at_award = await delivery.scores_for(
        vendors[k]["vendor_id"] for k in set(awards.values())
    )
    detail = []
    for part_num, vendor_key in awards.items():
        line = next((l for l in rfq["lines"] if str(l.get("part_num")) == part_num), None)
        if not line:
            continue
        quote_lines = quotes.get(vendor_key, {}).get("lines", [])
        ql = next((l for l in quote_lines if str(l.get("part_num")) == part_num), {})
        unit = ql.get("unit_price")
        last = line.get("last_price")
        detail.append({
            "part_num": part_num,
            "item_code": line.get("item_code", part_num),
            "name": line.get("name", ""),
            "qty": line.get("qty"),
            "vendor_key": vendor_key,
            "vendor_name": vendors[vendor_key]["name"],
            "vendor_otd_pct": (
                otd_at_award.get(vendors[vendor_key]["vendor_id"], {}) or {}
            ).get("otd_pct"),
            "unit_price": unit,
            "amount": round(unit * float(line.get("qty") or 0), 2) if unit is not None else None,
            "last_price": last,
            "vs_last_pct": (
                round((unit - last) / last * 100, 2) if unit is not None and last else None
            ),
        })

    updated = await db[schema.RFQS].find_one_and_update(
        {"_id": rfq["_id"]},
        {"$set": {
            "status": "awarded", "awards": detail, "award_reason": payload.reason,
            "awarded_at": utcnow(), "awarded_by": user["email"],
        }},
        return_document=ReturnDocument.AFTER,
    )

    # ราคาที่ชนะกลายเป็นราคาอ้างอิงล่าสุดของผู้ขายรายนั้น (เก็บฝั่งแอป ไม่แตะข้อมูล ETL)
    for row in detail:
        if row["unit_price"] is None:
            continue
        await db[schema.VENDOR_ITEMS].update_one(
            {"vendor_key": row["vendor_key"], "part_num": row["part_num"]},
            {
                "$set": {
                    "unit_price": row["unit_price"],
                    "currency": rfq.get("currency", "THB"),
                    "last_quoted_at": utcnow(),
                    "last_rfq_no": rfq.get("rfq_no"),
                },
                "$setOnInsert": {"created_at": utcnow(), "note": ""},
            },
            upsert=True,
        )

    await db[schema.AUDIT_LOGS].insert_one({
        "at": utcnow(), "by": user["email"], "action": "rfq.award",
        "rfq_no": rfq.get("rfq_no"), "awards": serialize(detail), "reason": payload.reason,
    })
    return serialize(updated)


@router.post("/{rfq_id}/close", summary="ปิดรับราคา")
async def close_rfq(
    rfq_id: str, payload: CloseRequest, user: Dict[str, Any] = Depends(require_buyer)
):
    updated = await get_database()[schema.RFQS].find_one_and_update(
        {"_id": to_oid(rfq_id, "rfq_id")},
        {"$set": {
            "status": "closed", "closed_at": utcnow(),
            "closed_by": user["email"], "close_reason": payload.reason,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ RFQ")
    return serialize(updated)


@router.delete("/{rfq_id}", summary="ลบ RFQ (admin)")
async def delete_rfq(rfq_id: str, user: Dict[str, Any] = Depends(require_admin)):
    db = get_database()
    oid = to_oid(rfq_id, "rfq_id")
    rfq = await db[schema.RFQS].find_one({"_id": oid})
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบ RFQ")
    if rfq.get("status") == "awarded":
        raise HTTPException(status.HTTP_409_CONFLICT, "RFQ ที่ประกาศผลแล้วลบไม่ได้")

    await db[schema.RFQS].delete_one({"_id": oid})
    await db[schema.RFQ_INVITES].delete_many({"rfq_id": oid})
    await db[schema.RFQ_QUOTES].delete_many({"rfq_id": oid})
    return {"ok": True}
