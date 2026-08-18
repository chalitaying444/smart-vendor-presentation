"""ความตรงเวลาในการส่งของผู้ขาย (On-Time Delivery)

อ่านจาก ``deliveries`` และ ``vendor_delivery`` ที่สร้างโดย
``scripts/05_delivery_performance.py --to-mongo`` ของโปรเจกต์ epicorExploreData
อ่านอย่างเดียวเช่นเดียวกับข้อมูล Epicor ชุดอื่น

หน่วยที่วัดคือ **งวดส่งของ (PO Release)** ไม่ใช่ทั้งใบ PO เพราะสินค้าบรรทัดเดียว
อาจแบ่งส่งหลายงวด และแต่ละงวดมีวันกำหนดของตัวเอง

**สิ่งที่ตั้งใจให้ระวังตอนเอาไปตัดสินใจ** (ตาม docs/delivery_date.md ข้อ 7)

* ผู้ขายที่มีงวดน้อย เปอร์เซ็นต์จะแกว่งมาก — ติดธง ``reliable`` ไว้ให้เห็น
  ไม่ใช่เอา 100% จากงวดเดียวไปเทียบกับ 92% จาก 200 งวด
* งวดที่ยังไม่ส่งไม่ถูกนับทั้งบวกและลบ จึงต้องโชว์ ``overdue_releases`` คู่กันเสมอ
  ไม่งั้นผู้ขายที่ดองงานไว้จะได้ OTD สวยเกินจริง
* การเลื่อนกำหนดทำให้ตัวเลขดูดีขึ้น — เก็บ ``days_late_vs_original`` ไว้เทียบ
* ``ReceiptDate`` คือวันที่คลังคีย์เข้าระบบ ไม่ใช่วันของมาถึงจริง ช้า 1–3 วัน
  อาจเป็นเรื่องกระบวนการภายใน ไม่ใช่ความผิดผู้ขาย
"""
import re
from typing import Any, Dict, Iterable, List, Optional

from app.db import schema
from app.db.mongodb import get_database

# ต่ำกว่านี้ถือว่าข้อมูลน้อยเกินกว่าจะสรุปนิสัยการส่งของผู้ขาย
MIN_RELIABLE_RELEASES = 5

# เกณฑ์แบ่งระดับ — ใช้ร่วมกันทั้งระบบเพื่อให้สีและคำอ่านตรงกันทุกหน้า
BANDS = (
    (95, "excellent", "ตรงเวลาดีมาก"),
    (85, "good", "ตรงเวลาดี"),
    (70, "fair", "พอใช้"),
    (0, "poor", "ต้องระวัง"),
)


def band(otd_pct: Optional[float], releases: int) -> Dict[str, str]:
    if otd_pct is None or releases <= 0:
        return {"level": "unknown", "label": "ยังไม่มีประวัติส่งของ"}
    if releases < MIN_RELIABLE_RELEASES:
        return {"level": "thin", "label": "ข้อมูลน้อย ({} งวด)".format(releases)}
    for threshold, level, label in BANDS:
        if otd_pct >= threshold:
            return {"level": level, "label": label}
    return {"level": "poor", "label": "ต้องระวัง"}


def score_view(doc: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """แปลงเอกสาร vendor_delivery เป็นรูปแบบที่หน้าบ้านใช้"""
    if not doc:
        return {
            "has_data": False, "otd_pct": None, "releases": 0, "on_time": 0, "late": 0,
            "avg_days_late": None, "median_days_late": None, "max_days_late": None,
            "overdue_releases": 0, "late_value": 0, "total_value": 0,
            "reliable": False, "first_delivery": None, "last_delivery": None,
            **band(None, 0),
        }

    releases = int(doc.get("releases") or 0)
    otd = doc.get("otdPct")
    return {
        "has_data": True,
        "otd_pct": otd,
        "releases": releases,
        "on_time": int(doc.get("onTime") or 0),
        "late": int(doc.get("late") or 0),
        "avg_days_late": doc.get("avgDaysLate"),
        # มัธยฐานสำคัญกว่าค่าเฉลี่ย เพราะงวดที่ช้าเป็นปีไม่กี่งวดดึงค่าเฉลี่ยเพี้ยนได้ง่าย
        "median_days_late": doc.get("medianDaysLate"),
        "max_days_late": doc.get("maxDaysLate"),
        "overdue_releases": int(doc.get("overdueReleases") or 0),
        "late_value": doc.get("lateValue") or 0,
        "total_value": doc.get("totalValue") or 0,
        "reliable": releases >= MIN_RELIABLE_RELEASES,
        "first_delivery": doc.get("firstDelivery"),
        "last_delivery": doc.get("lastDelivery"),
        **band(otd, releases),
    }


async def scores_for(vendor_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """ดึงคะแนนความตรงเวลาของผู้ขายหลายรายพร้อมกัน คีย์ด้วย vendorId"""
    ids = [str(v) for v in dict.fromkeys(vendor_ids) if str(v)]
    if not ids:
        return {}
    rows = await get_database()[schema.EP_VENDOR_DELIVERY].find(
        {"vendorId": {"$in": ids}}
    ).to_list(len(ids))
    return {str(r["vendorId"]): score_view(r) for r in rows}


async def score_for(vendor_id: str) -> Dict[str, Any]:
    doc = await get_database()[schema.EP_VENDOR_DELIVERY].find_one({"vendorId": str(vendor_id)})
    return score_view(doc)


async def attach_scores(rows: List[Dict[str, Any]], id_field: str = "vendor_id") -> None:
    """เติมฟิลด์ ``delivery`` ให้ทุกแถวที่มีรหัสผู้ขาย (แก้ไขในที่)"""
    if not rows:
        return
    scores = await scores_for(r.get(id_field) for r in rows)
    for row in rows:
        row["delivery"] = scores.get(str(row.get(id_field) or "")) or score_view(None)


# --------------------------------------------------------------- รายงวด
def delivery_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    vendor = doc.get("vendor") or {}
    part = doc.get("part") or {}
    qty = doc.get("qty") or {}
    return {
        "id": str(doc.get("_id", "")),
        "po_num": doc.get("poNum"),
        "po_line": doc.get("poLine"),
        "po_rel_num": doc.get("poRelNum"),
        "vendor_id": str(vendor.get("id") or ""),
        "vendor_key": "epicor:{}".format(vendor.get("id") or ""),
        "vendor_name": vendor.get("name", ""),
        "part_num": part.get("num", ""),
        "part_description": part.get("description", ""),
        "order_date": doc.get("orderDate"),
        "promise_date": doc.get("promiseDate"),
        # บอกด้วยว่าวันที่ใช้ตัดสินมาจากไหน — PromiseDt คือผู้ขายรับปาก ส่วน DueDate เป็นค่าวางแผน
        "promise_source": doc.get("promiseSource", ""),
        "due_date": doc.get("dueDate"),
        "first_receipt_date": doc.get("firstReceiptDate"),
        "last_receipt_date": doc.get("lastReceiptDate"),
        "qty_released": qty.get("released"),
        "qty_received": qty.get("received"),
        "qty_complete": bool(qty.get("complete")),
        "value": doc.get("value"),
        "delivered": bool(doc.get("delivered")),
        "on_time": bool(doc.get("onTime")),
        "days_late": doc.get("daysLate"),
        "overdue": bool(doc.get("overdue")),
        "days_overdue": doc.get("daysOverdue"),
        "rescheduled": bool(doc.get("rescheduled")),
        # ถ้าเคยเลื่อนกำหนด ตัวนี้คือความช้าจริงเมื่อเทียบกับวันที่ตกลงกันครั้งแรก
        "days_late_vs_original": doc.get("daysLateVsOriginal"),
        "status": doc.get("status", ""),
    }


SORTS = {
    "recent": ("promiseDate", -1),
    "latest": ("daysLate", -1),
    "earliest": ("daysLate", 1),     # ส่งเร็วกว่ากำหนดมากที่สุดขึ้นก่อน
    "overdue": ("daysOverdue", -1),
    "value": ("value", -1),
}


def build_query(
    vendor_id: Optional[str] = None,
    part_num: Optional[str] = None,
    q: str = "",
    only_late: bool = False,
    only_on_time: bool = False,
    only_overdue: bool = False,
    only_rescheduled: bool = False,
    min_days_late: Optional[int] = None,
) -> Dict[str, Any]:
    query: Dict[str, Any] = {}
    if vendor_id:
        query["vendor.id"] = str(vendor_id)
    if part_num:
        query["part.num"] = part_num
    if only_late:
        query["delivered"] = True
        query["onTime"] = False
    if only_on_time:
        query["delivered"] = True
        query["onTime"] = True
    if only_overdue:
        query["overdue"] = True
    if only_rescheduled:
        query["rescheduled"] = True
    if min_days_late is not None:
        # ค้างส่งยังไม่มี daysLate จึงต้องยอมให้ผ่านด้วย daysOverdue
        query["$or"] = [
            {"daysLate": {"$gte": min_days_late}},
            {"daysOverdue": {"$gte": min_days_late}},
        ]

    conds = []
    for token in str(q or "").split():
        rx = {"$regex": re.escape(token), "$options": "i"}
        or_block = [
            {"vendor.name": rx}, {"vendor.id": rx},
            {"part.num": rx}, {"part.description": rx},
        ]
        if token.isdigit():
            or_block.append({"poNum": int(token)})
        conds.append({"$or": or_block})
    if conds:
        query["$and"] = conds
    return query


async def deliveries(
    vendor_id: Optional[str] = None,
    part_num: Optional[str] = None,
    q: str = "",
    only_late: bool = False,
    only_on_time: bool = False,
    only_overdue: bool = False,
    only_rescheduled: bool = False,
    min_days_late: Optional[int] = None,
    sort: str = "recent",
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    query = build_query(vendor_id, part_num, q, only_late, only_on_time,
                        only_overdue, only_rescheduled, min_days_late)
    col = get_database()[schema.EP_DELIVERIES]
    field, direction = SORTS.get(sort) or SORTS["recent"]
    total = await col.count_documents(query)
    rows = await col.find(query).sort(field, direction).skip(skip).limit(limit).to_list(limit)
    return {
        "total": total, "skip": skip, "limit": limit,
        "has_more": skip + len(rows) < total,
        "items": [delivery_view(r) for r in rows],
    }


async def status_breakdown(vendor_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """นับงวดแยกตามสถานะ (ตรงเวลา / ช้า 1-7 วัน / ...) ของผู้ขายรายนั้นหรือทั้งบริษัท"""
    query: Dict[str, Any] = {}
    if vendor_id:
        query["vendor.id"] = str(vendor_id)

    counts: Dict[str, Dict[str, Any]] = {}
    async for row in get_database()[schema.EP_DELIVERIES].find(
        query, {"status": 1, "value": 1}
    ):
        label = row.get("status") or "ไม่ระบุ"
        entry = counts.setdefault(label, {"status": label, "releases": 0, "value": 0.0})
        entry["releases"] += 1
        entry["value"] += float(row.get("value") or 0)

    rows = sorted(counts.values(), key=lambda r: -r["releases"])
    total = sum(r["releases"] for r in rows) or 1
    for r in rows:
        r["value"] = round(r["value"], 2)
        r["percent"] = round(r["releases"] * 100 / total, 1)
    return rows


async def item_vendor_delivery(part_num: str) -> Dict[str, Dict[str, Any]]:
    """ประวัติการส่งของ *สินค้ารหัสนี้โดยเฉพาะ* แยกตามผู้ขาย

    ต่างจากคะแนนรวมของผู้ขาย — บางรายส่งของทั่วไปตรงเวลา แต่ช้าเฉพาะสินค้าบางตัว
    """
    rows = await get_database()[schema.EP_DELIVERIES].find(
        {"part.num": part_num, "delivered": True},
        {"vendor": 1, "onTime": 1, "daysLate": 1, "lastReceiptDate": 1},
    ).to_list(2000)

    by_vendor: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        vid = str((r.get("vendor") or {}).get("id") or "")
        if not vid:
            continue
        entry = by_vendor.setdefault(vid, {"releases": 0, "on_time": 0, "days": [], "last": None})
        entry["releases"] += 1
        entry["on_time"] += 1 if r.get("onTime") else 0
        if r.get("daysLate") is not None:
            entry["days"].append(float(r["daysLate"]))
        date = r.get("lastReceiptDate")
        if date and (entry["last"] is None or date > entry["last"]):
            entry["last"] = date

    out = {}
    for vid, e in by_vendor.items():
        days = sorted(e["days"])
        median = None
        if days:
            mid = len(days) // 2
            median = days[mid] if len(days) % 2 else round((days[mid - 1] + days[mid]) / 2, 1)
        out[vid] = {
            "releases": e["releases"],
            "on_time": e["on_time"],
            "otd_pct": round(e["on_time"] * 100 / e["releases"], 1),
            "median_days_late": median,
            "max_days_late": max(days) if days else None,
            "last_delivery": e["last"],
        }
    return out


async def group_by_vendor(
    q: str = "",
    only_late: bool = False,
    only_on_time: bool = False,
    only_overdue: bool = False,
    only_rescheduled: bool = False,
    min_days_late: Optional[int] = None,
    sort: str = "releases",
    limit: int = 100,
) -> Dict[str, Any]:
    """รวมงวดส่งของ **แยกเป็นรายผู้ขาย** พร้อมตัวอย่างงวดของแต่ละราย

    ใช้ตอบคำถาม "ใครค้างงานเราอยู่บ้าง เป็นของอะไร" และในทางกลับกัน
    "ใครส่งตรงเวลาให้เราบ้าง" — ต่างจากหน้าผู้ขายที่ต้องเปิดทีละราย

    ตัวอย่างที่หยิบมาโชว์จะเรียงตามมุมที่กำลังดู: ถ้าดูงานที่มีปัญหาจะเอาที่แย่สุดขึ้นก่อน
    ถ้าดูงานที่ส่งตรงเวลาจะเอาที่ส่งเร็วกว่ากำหนดมากสุดขึ้นก่อน
    """
    query = build_query(
        q=q, only_late=only_late, only_on_time=only_on_time,
        only_overdue=only_overdue, only_rescheduled=only_rescheduled,
        min_days_late=min_days_late,
    )
    rows = await get_database()[schema.EP_DELIVERIES].find(query).to_list(20000)

    grouped: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        vendor = r.get("vendor") or {}
        vid = str(vendor.get("id") or "")
        if not vid:
            continue
        entry = grouped.setdefault(vid, {
            "vendor_id": vid,
            "vendor_key": "epicor:{}".format(vid),
            "vendor_name": vendor.get("name", ""),
            "releases": 0, "value": 0.0, "worst_days": 0,
            "rescheduled": 0, "items": [],
        })
        entry["releases"] += 1
        entry["value"] += float(r.get("value") or 0)
        if r.get("rescheduled"):
            entry["rescheduled"] += 1
        days = r.get("daysOverdue") if only_overdue else r.get("daysLate")
        if only_on_time:
            # มุมนี้ "ดี" คือติดลบมาก จึงเก็บค่าที่เร็วที่สุดแทนค่าที่มากที่สุด
            entry["worst_days"] = min(entry["worst_days"], int(days or 0))
        else:
            entry["worst_days"] = max(entry["worst_days"], int(days or 0))
        entry["items"].append(delivery_view(r))

    key = "days_overdue" if only_overdue else "days_late"
    for entry in grouped.values():
        entry["items"].sort(key=lambda d: (d.get(key) or 0), reverse=not only_on_time)
        entry["items"] = entry["items"][:5]      # ตัวอย่าง ที่เหลือกดเข้าไปดูในหน้าผู้ขาย
        entry["value"] = round(entry["value"], 2)

    order = {
        "releases": lambda e: (-e["releases"], -e["value"]),
        "days": (lambda e: e["worst_days"]) if only_on_time else (lambda e: -e["worst_days"]),
        "value": lambda e: -e["value"],
    }
    vendors = sorted(grouped.values(), key=order.get(sort) or order["releases"])[:limit]
    await attach_scores(vendors)
    return {
        "total_vendors": len(grouped),
        "total_releases": sum(e["releases"] for e in grouped.values()),
        "total_value": round(sum(e["value"] for e in grouped.values()), 2),
        "vendors": vendors,
    }


async def company_summary() -> Dict[str, Any]:
    """ภาพรวมการส่งของทั้งบริษัท — ใช้ในหน้าภาพรวม (คำนวณวันละครั้ง)"""
    db = get_database()
    col = db[schema.EP_DELIVERIES]

    total = await col.count_documents({})
    if total == 0:
        return {"has_data": False}

    measured = await col.count_documents({"delivered": True, "daysLate": {"$ne": None}})
    on_time = await col.count_documents(
        {"delivered": True, "daysLate": {"$ne": None}, "onTime": True}
    )
    overdue = await col.count_documents({"overdue": True})

    worst = await db[schema.EP_VENDOR_DELIVERY].find(
        {"releases": {"$gte": MIN_RELIABLE_RELEASES}}
    ).sort("otdPct", 1).limit(8).to_list(8)
    best = await db[schema.EP_VENDOR_DELIVERY].find(
        {"releases": {"$gte": MIN_RELIABLE_RELEASES}}
    ).sort("otdPct", -1).limit(8).to_list(8)

    overdue_rows = await col.find({"overdue": True}).sort("daysOverdue", -1).limit(10).to_list(10)

    return {
        "has_data": True,
        "releases": total,
        "measured": measured,
        "on_time": on_time,
        "otd_pct": round(on_time * 100 / measured, 1) if measured else None,
        "overdue_releases": overdue,
        "min_reliable_releases": MIN_RELIABLE_RELEASES,
        "worst_vendors": [
            dict(score_view(v), vendor_id=str(v.get("vendorId") or ""),
                 vendor_key="epicor:{}".format(v.get("vendorId") or ""), name=v.get("name", ""))
            for v in worst
        ],
        "best_vendors": [
            dict(score_view(v), vendor_id=str(v.get("vendorId") or ""),
                 vendor_key="epicor:{}".format(v.get("vendorId") or ""), name=v.get("name", ""))
            for v in best
        ],
        "most_overdue": [delivery_view(r) for r in overdue_rows],
        "by_status": await status_breakdown(),
    }
