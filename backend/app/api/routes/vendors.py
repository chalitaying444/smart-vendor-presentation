"""ผู้ขาย — รายชื่อ รายละเอียด สินค้าที่เคยขาย และรายการเคลื่อนไหว

ข้อมูลมาจาก ``vendors`` ของ epicor_procurement ทั้งหมด (อ่านอย่างเดียว)
ส่วนที่ทีมจัดซื้อบันทึกเองอยู่ใน ``app_vendor_notes`` และถูกซ้อนทับตอนอ่าน
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from app.api.deps import get_current_user, require_buyer
from app.db import schema
from app.db.mongodb import get_database
from app.models.common import serialize, utcnow
from app.models.vendor import VendorNoteUpdate
from app.services import delivery, epicor
from app.services import vendor_directory as vd

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("", summary="รายชื่อผู้ขาย")
async def list_vendors(
    q: str = Query("", description="ชื่อ / รหัสผู้ขาย / เลขผู้เสียภาษี / ชื่อผู้ติดต่อ / อีเมล"),
    has_purchase: Optional[bool] = Query(None, description="true = เคยมีใบสั่งซื้อจริง"),
    has_email: Optional[bool] = Query(None, description="true = ติดต่อทางอีเมลได้"),
    active_only: bool = Query(False, description="true = ตัดผู้ขายที่ถูกปิดใช้งานออก"),
    sort: str = Query("amount", pattern="^(amount|name|recent|parts)$"),
    otd_max: Optional[float] = Query(
        None, ge=0, le=100, description="เอาเฉพาะรายที่ส่งตรงเวลาไม่เกิน % นี้ (ไว้ตามงานรายที่ช้า)"
    ),
    reliable_only: bool = Query(
        False, description="true = เฉพาะรายที่มีงวดส่งมากพอจะสรุปได้"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    result = await vd.search(
        q=q, has_purchase=has_purchase, has_email=has_email,
        active_only=active_only, sort=sort, skip=skip, limit=limit,
    )
    await delivery.attach_scores(result["items"])
    if otd_max is not None:
        result["items"] = [
            v for v in result["items"]
            if v["delivery"]["otd_pct"] is not None and v["delivery"]["otd_pct"] <= otd_max
        ]
    if reliable_only:
        result["items"] = [v for v in result["items"] if v["delivery"]["reliable"]]
    return serialize(result)


@router.get("/{vendor_key:path}/items", summary="สินค้าที่ผู้ขายรายนี้เคยขายให้เรา")
async def vendor_items(
    vendor_key: str,
    q: str = Query(""),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    _source, vendor_id = vd.parse_key(vendor_key)
    return serialize(await epicor.vendor_items(vendor_id, q=q, skip=skip, limit=limit))


@router.get("/{vendor_key:path}/transactions", summary="รายการเคลื่อนไหวของผู้ขายรายนี้")
async def vendor_transactions(
    vendor_key: str,
    doc_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    _source, vendor_id = vd.parse_key(vendor_key)
    if doc_type and doc_type not in schema.DOC_TYPE_LABEL:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "doc_type ไม่ถูกต้อง: {}".format(doc_type))
    result = await epicor.transactions(
        vendor_id=vendor_id, doc_type=doc_type, skip=skip, limit=limit
    )
    result["summary"] = await epicor.transaction_summary(vendor_id=vendor_id)
    return serialize(result)


@router.get(
    "/{vendor_key:path}/deliveries",
    summary="ประวัติการส่งของของผู้ขายรายนี้",
    description="หน่วยคืองวดส่งของ (PO Release) — กรองเฉพาะที่ส่งช้า ค้างส่ง หรือเคยเลื่อนกำหนดได้",
)
async def vendor_deliveries(
    vendor_key: str,
    only_late: bool = Query(False),
    only_overdue: bool = Query(False),
    only_rescheduled: bool = Query(False),
    sort: str = Query("recent", pattern="^(recent|latest|overdue|value)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    _source, vendor_id = vd.parse_key(vendor_key)
    result = await delivery.deliveries(
        vendor_id=vendor_id, only_late=only_late, only_overdue=only_overdue,
        only_rescheduled=only_rescheduled, sort=sort, skip=skip, limit=limit,
    )
    result["score"] = await delivery.score_for(vendor_id)
    result["by_status"] = await delivery.status_breakdown(vendor_id)
    return serialize(result)


@router.get("/{vendor_key:path}/contacts", summary="ผู้ติดต่อของผู้ขายรายนี้")
async def vendor_contacts(vendor_key: str, _: Dict[str, Any] = Depends(get_current_user)):
    return serialize(await vd.contacts_for(vendor_key))


@router.patch("/{vendor_key:path}/note", summary="บันทึกสถานะ/โน้ตภายในของผู้ขาย")
async def update_note(
    vendor_key: str,
    payload: VendorNoteUpdate = Body(...),
    user: Dict[str, Any] = Depends(require_buyer),
):
    _source, vendor_id = vd.parse_key(vendor_key)
    key = vd.make_key(vendor_id)
    await vd.get_one(key)      # 404 ถ้าไม่มีผู้ขายรายนี้จริง

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไม่มีข้อมูลที่จะบันทึก")
    changes.update(updated_at=utcnow(), updated_by=user.get("email", ""))

    await get_database()[schema.VENDOR_OVERRIDES].find_one_and_update(
        {"vendor_key": key},
        {"$set": changes, "$setOnInsert": {"vendor_key": key, "created_at": utcnow()}},
        upsert=True, return_document=ReturnDocument.AFTER,
    )
    return serialize(await vd.get_one(key))


@router.get("/{vendor_key:path}", summary="รายละเอียดผู้ขาย")
async def get_vendor(vendor_key: str, _: Dict[str, Any] = Depends(get_current_user)):
    vendor = await vd.get_one(vendor_key)
    vendor["delivery"] = await delivery.score_for(vendor["vendor_id"])
    vendor["delivery_by_status"] = await delivery.status_breakdown(vendor["vendor_id"])
    return serialize(vendor)
