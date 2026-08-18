"""หน้าเสนอราคาสำหรับผู้ขาย — เข้าถึงด้วย token ในลิงก์ ไม่ต้องมีบัญชีผู้ใช้

ผู้ขายทำได้สองอย่างตามที่ระบบกำหนด:
1. กรอกราคาทีละรายการในตารางออนไลน์
2. แนบไฟล์ใบเสนอราคาของบริษัทตัวเอง (PDF / Excel / รูป)

ทุก endpoint ในไฟล์นี้เป็นสาธารณะโดยเจตนา — token คือตัวยืนยันตัวตน
จึงต้องระวังไม่ให้ข้อมูลภายในรั่ว: ผู้ขายเห็นเฉพาะรายการของตัวเอง
ไม่เห็นราคาเป้าหมาย ไม่เห็นว่ามีผู้ขายรายอื่นถูกเชิญด้วย
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pymongo import ReturnDocument

from app.core.config import settings
from app.db import schema
from app.db.mongodb import get_database
from app.models.common import serialize, utcnow
from app.models.rfq import AcceptTermsRequest, DeclineRequest, QuoteSubmit
from app.services import filestore, storage, vendor_directory as vd
from app.services.rfq_doc import build_rfq_workbook

router = APIRouter(prefix="/portal", tags=["vendor-portal"])

QUOTE_SUBDIR = "quotes"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _load_invite(token: str, for_write: bool = False) -> Tuple[Dict, Dict]:
    db = get_database()
    invite = await db[schema.RFQ_INVITES].find_one({"token": token})
    if not invite:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ลิงก์ไม่ถูกต้องหรือถูกยกเลิกแล้ว")

    rfq = await db[schema.RFQS].find_one({"_id": invite["rfq_id"]})
    if not rfq:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบใบขอราคา")
    # โครงการถูกลบ = ใบนี้ถูกยกเลิกไปด้วย · ผู้ขายถือลิงก์อยู่ในมือแล้ว จึงต้องบอกให้ชัด
    # ว่ายกเลิกแล้ว ไม่ใช่ปล่อยให้เห็นหน้า error งง ๆ หรือแย่กว่านั้นคือกรอกราคาส่งเข้ามา
    # ให้โครงการที่ไม่มีอยู่แล้ว
    if rfq.get("deleted_at"):
        if for_write:
            raise HTTPException(
                status.HTTP_410_GONE,
                "ใบขอราคานี้ถูกยกเลิกแล้ว ไม่รับข้อมูลเพิ่ม — กรุณาติดต่อฝ่ายจัดซื้อ",
            )
        return invite, rfq
    if rfq.get("status") == "draft":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ใบขอราคานี้ยังไม่ได้ส่งออก")
    if for_write and rfq.get("status") in ("closed", "awarded", "cancelled"):
        raise HTTPException(status.HTTP_409_CONFLICT, "ใบขอราคานี้ปิดรับแล้ว ไม่สามารถแก้ไขข้อมูลได้")
    return invite, rfq


def _require_terms(invite: Dict) -> None:
    """กันไม่ให้ส่งราคาโดยยังไม่ได้รับทราบเงื่อนไข

    ตรวจฝั่งเซิร์ฟเวอร์ด้วย ไม่ใช่แค่ปิดปุ่มที่หน้าจอ — ไม่งั้นการติ๊กก็เป็นแค่พิธีกรรม
    """
    if not invite.get("terms_accepted_at"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "กรุณากดรับทราบเงื่อนไขการเสนอราคาก่อน",
        )


def _public_rfq(rfq: Dict, invite: Dict, quote: Optional[Dict]) -> Dict[str, Any]:
    """ตัดข้อมูลภายในออกก่อนส่งให้ผู้ขาย

    ก่อนกดรับทราบเงื่อนไข จะยังไม่ส่งเนื้อหาใบขอราคาออกไปเลย —
    ไม่มีชื่อสินค้า ไม่มีรหัส ไม่มีจำนวน ไม่มีแม้ชื่อผู้ขาย
    ตัดตั้งแต่ฝั่งเซิร์ฟเวอร์ ไม่ใช่แค่ซ่อนที่หน้าจอ เปิด DevTools ดูก็ไม่เห็น
    ส่งไปเท่าที่จำเป็นให้รู้ว่าลิงก์นี้คือใบไหน และต้องตอบภายในเมื่อไหร่
    """
    cancelled = bool(rfq.get("deleted_at"))
    # ยกเลิกแล้วก็ไม่ต้องส่งเนื้อหาใบออกไปอีก เหลือแค่บอกว่าเป็นใบไหนและยกเลิกแล้ว
    if cancelled:
        return serialize({
            "rfq_no": rfq.get("rfq_no", ""),
            "status": "cancelled",
            "cancelled": True,
            "locked": True,
            "line_count": len(rfq.get("lines") or []),
            "invite_status": invite.get("status", "sent"),
            "terms": [],
        })

    accepted = bool(invite.get("terms_accepted_at"))
    payload: Dict[str, Any] = {
        "cancelled": False,
        "rfq_no": rfq.get("rfq_no", ""),
        "status": rfq.get("status", ""),
        "due_date": rfq.get("due_date"),
        "line_count": len(rfq.get("lines") or []),
        "invite_status": invite.get("status", "sent"),
        "terms": settings.portal_terms,
        "terms_version": settings.PORTAL_TERMS_VERSION,
        # ผู้ขายต้องกดรับทราบก่อน ระบบจึงจะเปิดข้อมูล — เก็บเวลาไว้เป็นหลักฐาน
        "terms_accepted_at": invite.get("terms_accepted_at"),
        "terms_accepted_version": invite.get("terms_accepted_version", ""),
        "locked": not accepted,
    }
    if not accepted:
        return serialize(payload)

    lines = []
    for line in rfq.get("lines", []):
        lines.append(
            {
                "part_num": str(line.get("part_num", "")),
                "item_code": line.get("item_code", ""),
                "name": line.get("name", ""),
                "description": line.get("description", ""),
                "manufacturer": line.get("manufacturer", ""),
                "mpn": line.get("mpn", ""),
                "specs": line.get("specs", {}),
                "qty": line.get("qty", 0),
                "uom": line.get("uom", ""),
                "required_date": line.get("required_date"),
                "remark": line.get("remark", ""),
            }
        )
    payload.update(
        {
            "title": rfq.get("title", ""),
            "currency": rfq.get("currency", "THB"),
            "incoterm": rfq.get("incoterm", ""),
            "payment_terms": rfq.get("payment_terms", ""),
            "delivery_place": rfq.get("delivery_place", ""),
            "note": rfq.get("note", ""),
            "message": invite.get("message", ""),
            "lines": lines,
            "vendor": {
                "vendor_key": invite.get("vendor_key", ""),
                "name": invite.get("vendor_name", ""),
                "contact_name": invite.get("contact_name", ""),
                "contact_email": invite.get("contact_email", ""),
            },
            "rfq_document_url": "/api/portal/{}/document".format(invite["token"]),
            "vat_percent": rfq.get("vat_percent", 7),
            "quote": quote,
        }
    )
    return serialize(payload)


@router.get("/{token}", summary="เปิดใบขอราคาด้วยลิงก์ที่ได้รับ")
async def open_portal(token: str):
    db = get_database()
    invite, rfq = await _load_invite(token)

    if invite.get("status") in ("pending", "sent"):
        invite = await db[schema.RFQ_INVITES].find_one_and_update(
            {"_id": invite["_id"]},
            {"$set": {"status": "viewed", "viewed_at": invite.get("viewed_at") or utcnow()}},
            return_document=ReturnDocument.AFTER,
        )

    quote = await db[schema.RFQ_QUOTES].find_one(
        {"rfq_id": rfq["_id"], "vendor_key": invite["vendor_key"]}
    )
    return _public_rfq(rfq, invite, serialize(quote))


@router.get("/{token}/document", summary="ดาวน์โหลดใบขอราคา (Excel)")
async def download_document(token: str):
    db = get_database()
    invite, rfq = await _load_invite(token)
    # เช็ค "ยกเลิกแล้ว" ก่อนเรื่องเงื่อนไข — ใบที่ยกเลิกแล้วต้องตอบว่ายกเลิกเสมอ
    # ไม่ใช่ไปบอกว่า "กดรับทราบเงื่อนไขก่อน" ทั้งที่กดไปก็ไม่ได้อะไรแล้ว
    if rfq.get("deleted_at"):
        raise HTTPException(status.HTTP_410_GONE, "ใบขอราคานี้ถูกยกเลิกแล้ว")
    # ไฟล์นี้มีรายการสินค้าครบ ถ้าไม่กันไว้ การซ่อนบนหน้าจอก็ไม่มีความหมาย
    _require_terms(invite)

    document = invite.get("rfq_document")
    if not document or not document.get("file_id") or not await filestore.stat(document["file_id"]):
        vendor = await vd.get_one(invite["vendor_key"])
        built = build_rfq_workbook(
            serialize(rfq), vendor, serialize(invite), invite.get("message", "")
        )
        document = await filestore.put(
            built["data"], filename=built["filename"], content_type=built["content_type"],
            kind="rfq_doc", ref=rfq.get("rfq_no", ""),
        )
        await db[schema.RFQ_INVITES].update_one(
            {"_id": invite["_id"]}, {"$set": {"rfq_document": document}}
        )

    return filestore.response(await filestore.read(document["file_id"]))


@router.post(
    "/{token}/accept-terms",
    summary="ผู้ขายกดรับทราบเงื่อนไขก่อนเสนอราคา",
    description="บันทึกเวลาและเวอร์ชันของเงื่อนไขที่รับทราบ เพื่อใช้อ้างอิงภายหลัง",
)
async def accept_terms(token: str, payload: AcceptTermsRequest):
    db = get_database()
    invite, _rfq = await _load_invite(token, for_write=True)
    if not payload.accepted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ต้องติ๊กยอมรับเงื่อนไขก่อนจึงจะเสนอราคาได้")

    updated = await db[schema.RFQ_INVITES].find_one_and_update(
        {"_id": invite["_id"]},
        {"$set": {
            "terms_accepted_at": utcnow(),
            "terms_accepted_version": settings.PORTAL_TERMS_VERSION,
            "terms_accepted_by": payload.accepted_by,
        }},
        return_document=ReturnDocument.AFTER,
    )
    return {
        "ok": True,
        "terms_accepted_at": serialize(updated.get("terms_accepted_at")),
        "terms_accepted_version": updated.get("terms_accepted_version", ""),
    }


@router.post("/{token}/quote", summary="บันทึกราคาที่เสนอ (ส่งซ้ำได้จนกว่า RFQ จะปิด)")
async def submit_quote(token: str, payload: QuoteSubmit):
    from app.api.routes.rfqs import to_dt

    db = get_database()
    invite, rfq = await _load_invite(token, for_write=True)
    _require_terms(invite)

    lines_by_item = {str(l.get("part_num", "")): l for l in rfq.get("lines", [])}
    unknown = [l.part_num for l in payload.lines if l.part_num not in lines_by_item]
    if unknown:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "มีรายการที่ไม่ได้อยู่ในใบขอราคานี้: {}".format(", ".join(unknown)),
        )

    lines: List[Dict[str, Any]] = []
    subtotal = 0.0
    for ql in payload.lines:
        rfq_line = lines_by_item[ql.part_num]
        qty = float(rfq_line.get("qty") or 0)
        amount = None
        if not ql.no_quote and ql.unit_price is not None:
            amount = round(ql.unit_price * qty, 2)
            subtotal += amount
        row = ql.model_dump()
        row.update(
            item_code=rfq_line.get("item_code", ""),
            name=rfq_line.get("name", ""),
            qty=qty,
            uom=rfq_line.get("uom", ""),
            amount=amount,
        )
        lines.append(row)

    subtotal = round(subtotal, 2)
    vat_amount = round(subtotal * payload.vat_percent / 100, 2)

    existing = await db[schema.RFQ_QUOTES].find_one(
        {"rfq_id": rfq["_id"], "vendor_key": invite["vendor_key"]}, {"attachments": 1}
    )
    doc = {
        "rfq_id": rfq["_id"],
        "rfq_no": rfq.get("rfq_no", ""),
        "vendor_key": invite["vendor_key"],
        "source": invite.get("source", ""),
        "vendor_id": invite.get("vendor_id", ""),
        "vendor_name": invite.get("vendor_name", ""),
        "lines": lines,
        "currency": payload.currency,
        "subtotal": subtotal,
        "vat_percent": payload.vat_percent,
        "vat_amount": vat_amount,
        "total": round(subtotal + vat_amount, 2),
        "valid_until": to_dt(payload.valid_until),
        "payment_terms": payload.payment_terms,
        "incoterm": payload.incoterm,
        "delivery_days": payload.delivery_days,
        "contact_name": payload.contact_name or invite.get("contact_name", ""),
        "contact_email": payload.contact_email or invite.get("contact_email", ""),
        "contact_phone": payload.contact_phone,
        "note": payload.note,
        "attachments": (existing or {}).get("attachments", []),
        "submitted_at": utcnow(),
    }
    quote = await db[schema.RFQ_QUOTES].find_one_and_update(
        {"rfq_id": rfq["_id"], "vendor_key": invite["vendor_key"]},
        {"$set": doc, "$setOnInsert": {"created_at": utcnow()}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    await db[schema.RFQ_INVITES].update_one(
        {"_id": invite["_id"]}, {"$set": {"status": "quoted", "responded_at": utcnow()}}
    )
    return serialize(quote)


@router.post(
    "/{token}/attachments",
    status_code=status.HTTP_201_CREATED,
    summary="แนบใบเสนอราคาของผู้ขาย (PDF / Excel / รูป)",
)
async def upload_attachment(token: str, file: UploadFile = File(...)):
    db = get_database()
    invite, rfq = await _load_invite(token, for_write=True)
    _require_terms(invite)

    saved = await storage.save_upload(
        file, QUOTE_SUBDIR, storage.QUOTE_SUFFIXES, ref=rfq.get("rfq_no", ""),
    )
    attachment = {
        "file_id": saved["file_id"],
        # ลิงก์ของผู้ขายผูกกับ token ของเขาเอง — เปิดไฟล์ของรายอื่นด้วยลิงก์นี้ไม่ได้
        "url": "/api/portal/{}/attachments/{}".format(token, saved["file_id"]),
        "filename": saved["filename"],
        "size": saved["size"],
        "content_type": saved["content_type"],
        "sha256": saved["sha256"],
        "uploaded_at": utcnow(),
    }

    quote = await db[schema.RFQ_QUOTES].find_one_and_update(
        {"rfq_id": rfq["_id"], "vendor_key": invite["vendor_key"]},
        {
            "$push": {"attachments": attachment},
            "$setOnInsert": {
                "rfq_no": rfq.get("rfq_no", ""),
                "source": invite.get("source", ""),
                "vendor_id": invite.get("vendor_id", ""),
                "vendor_name": invite.get("vendor_name", ""),
                "lines": [], "currency": rfq.get("currency", "THB"),
                "subtotal": 0, "vat_percent": 7, "vat_amount": 0, "total": 0,
                "created_at": utcnow(), "submitted_at": None,
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return {
        "attachment": serialize(attachment),
        "attachments": serialize(quote.get("attachments", [])),
    }


@router.get("/{token}/attachments/{file_id}", summary="โหลดไฟล์แนบของผู้ขายรายนี้")
async def download_attachment(token: str, file_id: str):
    """ผู้ขายเปิดไฟล์ที่ตัวเองแนบไว้ได้ แต่ต้องเป็นไฟล์ที่อยู่ในใบเสนอราคาของตัวเองเท่านั้น

    ตรวจจากรายการไฟล์แนบในใบของเขาจริง ๆ ไม่ใช่แค่ยิง id ตรงไปที่ตัวเก็บไฟล์ —
    ไม่งั้นผู้ขายรายหนึ่งที่เดา id ถูกจะเปิดใบเสนอราคาของคู่แข่งได้
    """
    db = get_database()
    invite, rfq = await _load_invite(token)
    _require_terms(invite)

    quote = await db[schema.RFQ_QUOTES].find_one(
        {"rfq_id": rfq["_id"], "vendor_key": invite["vendor_key"]}, {"attachments": 1}
    )
    owned = {str(a.get("file_id")) for a in (quote or {}).get("attachments", [])}
    if file_id not in owned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบไฟล์แนบนี้ในใบเสนอราคาของท่าน")

    return filestore.response(await filestore.read(file_id))


@router.delete("/{token}/attachments/{file_id}", summary="ลบไฟล์แนบ")
async def delete_attachment(token: str, file_id: str):
    db = get_database()
    invite, rfq = await _load_invite(token, for_write=True)

    quote = await db[schema.RFQ_QUOTES].find_one_and_update(
        {"rfq_id": rfq["_id"], "vendor_key": invite["vendor_key"]},
        {"$pull": {"attachments": {"file_id": file_id}}},
        return_document=ReturnDocument.AFTER,
    )
    if not quote:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ยังไม่มีใบเสนอราคา")
    # ลบเนื้อไฟล์ทิ้งด้วย ไม่ใช่แค่ถอดชื่อออกจากรายการแล้วปล่อยไฟล์ค้างในฐานข้อมูลตลอดไป
    await filestore.delete(file_id)
    return {"ok": True, "attachments": serialize(quote.get("attachments", []))}


@router.post("/{token}/decline", summary="แจ้งว่าไม่ขอเสนอราคาใบนี้")
async def decline(token: str, payload: DeclineRequest):
    db = get_database()
    invite, _rfq = await _load_invite(token, for_write=True)
    await db[schema.RFQ_INVITES].update_one(
        {"_id": invite["_id"]},
        {"$set": {
            "status": "declined", "responded_at": utcnow(), "decline_reason": payload.reason,
        }},
    )
    return {"ok": True}
