"""ตามงานส่งของ — ดูว่างวดไหนช้า ของใคร เป็นของอะไร

หน้าผู้ขายตอบได้ทีละราย ส่วนตรงนี้ตอบคำถาม "ตอนนี้มีอะไรค้างอยู่บ้าง"
ข้ามผู้ขายทั้งหมดในที่เดียว เพื่อให้ไล่ตามงานได้จริง
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.common import serialize
from app.services import delivery

router = APIRouter(prefix="/deliveries", tags=["deliveries"])


@router.get(
    "",
    summary="รายการงวดส่งของ (ค้นข้ามผู้ขายทั้งหมด)",
    description=(
        "ค้นด้วยชื่อผู้ขาย รหัสผู้ขาย รหัส/ชื่อสินค้า หรือเลข PO · "
        "กรองเฉพาะที่ส่งช้า ยังค้างส่ง หรือเคยเลื่อนกำหนด"
    ),
)
async def list_deliveries(
    q: str = Query("", description="ชื่อผู้ขาย / รหัสสินค้า / คำอธิบาย / เลข PO"),
    vendor_id: Optional[str] = Query(None),
    part_num: Optional[str] = Query(None),
    only_late: bool = Query(False, description="เฉพาะที่รับของแล้วแต่ช้ากว่ากำหนด"),
    only_on_time: bool = Query(False, description="เฉพาะที่ส่งตรงเวลา (หรือก่อนกำหนด)"),
    only_overdue: bool = Query(False, description="เฉพาะที่เลยกำหนดแล้วยังไม่ได้รับของ"),
    only_rescheduled: bool = Query(False, description="เฉพาะที่เคยเลื่อนกำหนด"),
    min_days_late: Optional[int] = Query(None, ge=0, description="ช้าอย่างน้อยกี่วัน"),
    sort: Optional[str] = Query(
        None,
        pattern="^(recent|latest|earliest|overdue|value)$",
        description="ไม่ระบุ = เลือกให้อัตโนมัติตามมุมที่ดู (ค้างส่ง→ค้างนานสุด, ตรงเวลา→เร็วสุด, ช้า→ช้าสุด)",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    # ค่าเริ่มต้นต้องตรงกับสิ่งที่คนดูอยากเห็นก่อน ไม่ใช่บังคับให้ระบุเองทุกครั้ง
    if sort is None:
        sort = ("overdue" if only_overdue
                else "earliest" if only_on_time
                else "latest" if only_late
                else "recent")

    result = await delivery.deliveries(
        vendor_id=vendor_id, part_num=part_num, q=q,
        only_late=only_late, only_on_time=only_on_time,
        only_overdue=only_overdue, only_rescheduled=only_rescheduled,
        min_days_late=min_days_late, sort=sort, skip=skip, limit=limit,
    )
    return serialize(result)


@router.get(
    "/by-vendor",
    summary="สรุปงวดส่งของ แยกรายผู้ขาย",
    description=(
        "รวมงวดตามเงื่อนไขที่เลือก (ช้า / ตรงเวลา / ค้างส่ง / เคยเลื่อนกำหนด) เป็นรายผู้ขาย "
        "พร้อมตัวอย่าง 5 งวดของแต่ละราย"
    ),
)
async def by_vendor(
    q: str = Query(""),
    only_late: bool = Query(False),
    only_on_time: bool = Query(False),
    only_overdue: bool = Query(False),
    only_rescheduled: bool = Query(False),
    min_days_late: Optional[int] = Query(None, ge=0),
    sort: str = Query("releases", pattern="^(releases|days|value)$"),
    limit: int = Query(100, ge=1, le=300),
    _: Dict[str, Any] = Depends(get_current_user),
):
    return serialize(await delivery.group_by_vendor(
        q=q, only_late=only_late, only_on_time=only_on_time,
        only_overdue=only_overdue, only_rescheduled=only_rescheduled,
        min_days_late=min_days_late, sort=sort, limit=limit,
    ))


@router.get("/summary", summary="ตัวเลขสรุปการส่งของทั้งบริษัท")
async def summary(_: Dict[str, Any] = Depends(get_current_user)):
    return serialize(await delivery.company_summary())
