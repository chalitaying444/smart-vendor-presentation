"""แคตตาล็อกสินค้า — ค้นหา ดูราคาล่าสุด และเรียกดูรายการเคลื่อนไหวของแต่ละรหัส

ทุกอย่างในไฟล์นี้อ่านจาก ``epicor_procurement`` โดยตรง ไม่มีการเขียนกลับ
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, require_buyer
from app.db import schema
from app.models.common import serialize
from app.services import delivery, epicor, snapshot
from app.services import vendor_directory as vd

router = APIRouter(prefix="/catalog", tags=["catalog"])

SNAP_OVERVIEW = "catalog.overview"
SNAP_FACETS = "catalog.facets"

# ชุดข้อมูลสรุปทั้งหมด + วิธีสร้าง — ใช้ตอนวอร์มตอนเปิดเซิร์ฟเวอร์ด้วย
SNAPSHOT_BUILDERS = {
    SNAP_OVERVIEW: epicor.overview,
    SNAP_FACETS: epicor.facets,
}


def _with_meta(snap: Dict[str, Any]) -> Dict[str, Any]:
    """แนบเวลาที่คำนวณไปกับข้อมูล เพื่อให้หน้าบ้านบอกผู้ใช้ได้ว่าข้อมูล ณ เมื่อไร"""
    data = dict(snap["data"] or {})
    data["snapshot"] = {
        "built_at": snap["built_at"],
        "age_hours": snap["age_hours"],
        "stale": snap["stale"],
        "next_refresh_at": snap["next_refresh_at"],
    }
    return data


@router.get(
    "/items",
    summary="ค้นหาสินค้า",
    description=(
        "ค้นแบบ *น่าจะใช่* ไม่ต้องตรงเป๊ะ — พิมพ์รหัสไม่มีขีดก็เจอ พิมพ์ผิดเล็กน้อยก็ยังเจอ "
        "และค้นด้วยชื่อผู้ขายได้ด้วย เว้นว่างไว้จะเห็นรายการสินค้าทันที เรียงตามมูลค่าที่เคยซื้อ"
    ),
)
async def list_items(
    q: str = Query("", description="รหัสสินค้า / คำอธิบาย / ยี่ห้อ / ชื่อผู้ขาย"),
    class_id: Optional[str] = Query(None, description="หมวดสินค้าจาก Epicor"),
    vendor_id: Optional[str] = Query(None, description="เฉพาะที่ผู้ขายรายนี้เคยขาย"),
    single_source: Optional[bool] = Query(None, description="true = มีผู้ขายรายเดียว"),
    price_volatile: Optional[bool] = Query(None, description="true = ราคาแกว่งผิดปกติ"),
    service: Optional[bool] = Query(None, description="true = งานบริการ (รหัสขึ้นต้น 03)"),
    has_price: Optional[bool] = Query(None, description="true = มีราคาล่าสุด"),
    sort: str = Query("relevance", pattern="^(relevance|amount|recent|times|part|spread)$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(40, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    result = await epicor.search_items(
        q=q, class_id=class_id, vendor_id=vendor_id, single_source=single_source,
        price_volatile=price_volatile, service=service, has_price=has_price,
        sort=sort, skip=skip, limit=limit,
    )
    return serialize(result)


@router.get("/suggest", summary="คำแนะนำระหว่างพิมพ์")
async def suggest(
    q: str = Query("", min_length=1),
    limit: int = Query(8, ge=1, le=20),
    _: Dict[str, Any] = Depends(get_current_user),
):
    result = await epicor.search_items(q=q, limit=limit)
    return serialize({
        "items": [
            {"part_num": i["part_num"], "description": i["description"],
             "last_price": i["last_price"], "vendor_count": i["vendor_count"]}
            for i in result["items"]
        ],
        "fuzzy_terms": result.get("fuzzy_terms") or [],
    })


@router.get(
    "/facets",
    summary="ตัวเลือกตัวกรอง + จำนวนข้อมูล",
    description="อ่านจากข้อมูลสรุปที่คำนวณไว้ล่วงหน้า อัปเดตวันละครั้ง",
)
async def catalog_facets(_: Dict[str, Any] = Depends(get_current_user)):
    snap = await snapshot.get(SNAP_FACETS, epicor.facets)
    return serialize(_with_meta(snap))


@router.get(
    "/overview",
    summary="ตัวเลขสรุปสำหรับหน้าภาพรวม",
    description=(
        "คำนวณล่วงหน้าเก็บไว้ที่ ``app_snapshots`` แล้วใช้ซ้ำจนกว่าจะครบ 24 ชั่วโมง "
        "— ข้อมูลต้นทางเปลี่ยนเฉพาะตอนรัน ETL จึงไม่ต้องกวาดใหม่ทุกครั้งที่เปิดหน้า"
    ),
)
async def overview(_: Dict[str, Any] = Depends(get_current_user)):
    snap = await snapshot.get(SNAP_OVERVIEW, epicor.overview)
    return serialize(_with_meta(snap))


@router.post(
    "/overview/refresh",
    summary="สั่งคำนวณข้อมูลสรุปใหม่ทันที",
    description="ใช้หลังรัน ETL รอบใหม่ ถ้าไม่อยากรอรอบอัปเดตประจำวัน",
)
async def refresh_overview(_: Dict[str, Any] = Depends(require_buyer)):
    await snapshot.build(SNAP_OVERVIEW, epicor.overview)
    await snapshot.build(SNAP_FACETS, epicor.facets)
    snap = await snapshot.get(SNAP_OVERVIEW, epicor.overview)
    return serialize(_with_meta(snap))


@router.get(
    "/items/{part_num:path}/transactions",
    summary="รายการเคลื่อนไหวของสินค้ารหัสนี้",
    description="ใบสั่งซื้อ / การรับของ / ใบแจ้งหนี้ ทั้งหมดที่อ้างถึงรหัสนี้ เรียงจากล่าสุด",
)
async def item_transactions(
    part_num: str,
    doc_type: Optional[str] = Query(None, description="PO_LINE / RECEIPT_LINE / AP_INVOICE_LINE"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    _: Dict[str, Any] = Depends(get_current_user),
):
    if doc_type and doc_type not in schema.DOC_TYPE_LABEL:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "doc_type ไม่ถูกต้อง: {} (ต้องเป็น {})".format(
                doc_type, " / ".join(schema.DOC_TYPE_LABEL)
            ),
        )
    result = await epicor.transactions(
        part_num=part_num, doc_type=doc_type, skip=skip, limit=limit
    )
    result["summary"] = await epicor.transaction_summary(part_num=part_num)
    return serialize(result)


@router.get("/items/{part_num:path}/price-history", summary="ประวัติราคาซื้อทุกครั้ง")
async def item_price_history(part_num: str, _: Dict[str, Any] = Depends(get_current_user)):
    return serialize({"part_num": part_num, "points": await epicor.price_history(part_num)})


@router.get("/items/{part_num:path}/vendors", summary="ผู้ขายที่เคยขายสินค้ารหัสนี้")
async def item_vendors(part_num: str, _: Dict[str, Any] = Depends(get_current_user)):
    item = await epicor.get_item(part_num)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบสินค้ารหัส {}".format(part_num))
    vendors = item.get("vendors", [])
    await _attach_delivery(part_num, vendors)
    return serialize({"part_num": part_num, "vendors": vendors})


async def _attach_delivery(part_num: str, vendors: list) -> None:
    """ติดคะแนนความตรงเวลาให้ผู้ขายแต่ละราย ทั้งภาพรวมและเฉพาะสินค้ารหัสนี้

    คนซื้อต้องเห็นสองอย่างพร้อมกัน: ราคา และความน่าเชื่อถือเรื่องเวลา
    ถ้าเห็นแต่ราคา จะเลือกเจ้าถูกสุดที่ส่งช้าประจำโดยไม่รู้ตัว
    """
    await delivery.attach_scores(vendors)
    per_item = await delivery.item_vendor_delivery(part_num)
    for v in vendors:
        v["delivery_this_item"] = per_item.get(str(v.get("vendor_id") or ""))


@router.get(
    "/items/{part_num:path}",
    summary="รายละเอียดสินค้า + ราคาล่าสุด + ผู้ขายทุกราย",
)
async def get_item(part_num: str, _: Dict[str, Any] = Depends(get_current_user)):
    item = await epicor.get_item(part_num)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบสินค้ารหัส {}".format(part_num))
    item["summary"] = await epicor.transaction_summary(part_num=part_num)
    await _attach_delivery(part_num, item.get("vendors", []))
    suggested = await vd.suggest_for_parts([part_num], limit=20)
    await delivery.attach_scores(suggested)
    item["suggested_vendors"] = suggested
    return serialize(item)
