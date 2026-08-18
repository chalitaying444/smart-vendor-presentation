"""ผู้ขายในมุมมองของงาน RFQ

ตอนนี้ผู้ขายมาจากแหล่งเดียวคือ ``vendors`` ของ epicor_procurement แล้ว
แต่ RFQ ยังอ้างผู้ขายด้วย **vendor_key** เหมือนเดิม (รูปแบบ ``epicor:<vendorId>``)
เพื่อไม่ให้ต้องแก้ใบขอราคาเดิมที่บันทึกไว้ และเผื่อวันหน้ามีแหล่งข้อมูลอื่นเพิ่ม

ข้อมูลที่ทีมจัดซื้อเพิ่มเอง (อนุมัติ / เรตติ้ง / โน้ต) เก็บแยกที่ ``app_vendor_notes``
แล้วซ้อนทับตอนอ่าน — ไม่แตะเอกสารของ ETL เลย เพราะ ETL จะล้างทิ้งทุกครั้งที่รัน
"""
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import HTTPException, status

from app.db import schema
from app.db.mongodb import get_database
from app.services import epicor

SOURCE = "epicor"
VALID_SOURCES = (SOURCE, "erp", "partner")   # ยอมรับคีย์รูปแบบเก่าไว้ด้วย


def make_key(vendor_id: Any) -> str:
    return "{}:{}".format(SOURCE, vendor_id)


def parse_key(vendor_key: str) -> Tuple[str, str]:
    """แยก ``epicor:21010236`` เป็น ("epicor", "21010236")

    ยอมรับทั้งแบบมี prefix และแบบส่ง vendorId มาเปล่า ๆ (เช่นลิงก์เก่า
    หรือ proxy ที่ตัด prefix ทิ้ง) เพื่อไม่ให้ URL ที่เคยใช้ได้กลายเป็น 400
    """
    raw = str(vendor_key or "").strip()
    source, sep, vendor_id = raw.partition(":")
    if sep and source in VALID_SOURCES:
        if not vendor_id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "vendor_key ไม่ถูกต้อง: {} (ขาดรหัสผู้ขายหลัง '{}:')".format(vendor_key, source),
            )
        return SOURCE, vendor_id
    if raw:
        return SOURCE, raw
    raise HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "vendor_key ไม่ถูกต้อง: {} (ต้องเป็น epicor:<รหัสผู้ขาย>)".format(vendor_key),
    )


async def load_overrides(vendor_keys: Iterable[str]) -> Dict[str, Dict]:
    keys = list(vendor_keys)
    if not keys:
        return {}
    rows = await get_database()[schema.VENDOR_OVERRIDES].find(
        {"vendor_key": {"$in": keys}}
    ).to_list(len(keys))
    return {r["vendor_key"]: r for r in rows}


def apply_override(vendor: Dict[str, Any], override: Optional[Dict]) -> Dict[str, Any]:
    merged = dict(vendor)
    merged.setdefault("source", SOURCE)
    merged.update(approval_status="pending", rating=0.0, system_note="",
                  blocked=False, preferred=False)
    if not override:
        return merged
    for field in ("approval_status", "rating", "system_note", "blocked", "preferred"):
        if override.get(field) is not None:
            merged[field] = override[field]
    if override.get("contacts"):
        merged["contacts"] = override["contacts"]
    return merged


def _for_rfq(vendor: Dict[str, Any]) -> Dict[str, Any]:
    """เติมฟิลด์ที่ชั้น RFQ คาดหวัง (name / source / vendor_id / emails / contacts)"""
    out = dict(vendor)
    out["source"] = SOURCE
    out.setdefault("emails", [])
    contacts = out.get("contacts") or []
    if not contacts and out["emails"]:
        contacts = [{"name": "", "email": e, "phone": "", "function": "",
                     "is_primary": i == 0} for i, e in enumerate(out["emails"])]
        out["contacts"] = contacts
    return out


async def get_many(vendor_keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    keys = list(dict.fromkeys(vendor_keys))
    if not keys:
        return {}
    ids = [parse_key(k)[1] for k in keys]
    found = await epicor.get_vendors(ids)

    out: Dict[str, Dict[str, Any]] = {}
    for vendor in found.values():
        out[vendor["vendor_key"]] = _for_rfq(vendor)

    overrides = await load_overrides(out.keys())
    return {k: apply_override(v, overrides.get(k)) for k, v in out.items()}


async def get_one(vendor_key: str) -> Dict[str, Any]:
    _source, vendor_id = parse_key(vendor_key)
    canonical = make_key(vendor_id)
    found = await get_many([canonical])
    if canonical not in found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ขาย {}".format(vendor_key))
    vendor = found[canonical]
    # หน้ารายละเอียดเท่านั้นที่ต้องรู้ว่ารหัสสินค้าที่ซื้อบ่อยคือของอะไร
    await epicor.enrich_top_parts([vendor])
    return vendor


async def search(
    q: str = "",
    has_email: Optional[bool] = None,
    has_purchase: Optional[bool] = None,
    active_only: bool = False,
    sort: str = "amount",
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    result = await epicor.search_vendors(
        q=q, has_purchase=has_purchase, has_email=has_email,
        active_only=active_only, sort=sort, skip=skip, limit=limit,
    )
    overrides = await load_overrides(v["vendor_key"] for v in result["items"])
    result["items"] = [
        apply_override(_for_rfq(v), overrides.get(v["vendor_key"])) for v in result["items"]
    ]
    return result


def primary_email(vendor: Dict[str, Any]) -> str:
    for contact in vendor.get("contacts", []):
        if contact.get("is_primary") and contact.get("email"):
            return contact["email"]
    emails = vendor.get("emails") or []
    return emails[0] if emails else ""


async def contacts_for(vendor_key: str) -> List[Dict[str, Any]]:
    vendor = await get_one(vendor_key)
    return [
        {
            "contact_name": c.get("name", ""),
            "position": c.get("function", ""),
            "emails": [c["email"]] if c.get("email") else [],
            "phones": [c["phone"]] if c.get("phone") else [],
            "product_note": "",
            "contact_type": c.get("function", ""),
        }
        for c in vendor.get("contacts", [])
    ]


async def suggest_for_parts(part_nums: List[str], limit: int = 40) -> List[Dict[str, Any]]:
    """ผู้ขายที่ "น่าจะเสนอราคาได้" สำหรับชุดรหัสสินค้าที่ระบุ

    ไม่ต้องเดา — Epicor บอกอยู่แล้วว่าใครเคยขายรหัสนี้ให้เรา
    เรียงตามจำนวนรายการที่ครอบคลุม แล้วตามด้วยราคาล่าสุดที่ถูกกว่า
    """
    if not part_nums:
        return []
    db = get_database()
    rows = await db[schema.EP_LAST_PRICE].find(
        {"partNum": {"$in": part_nums}}
    ).to_list(len(part_nums))

    agg: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        for v in row.get("vendors") or []:
            vid = str(v.get("vendorId") or "")
            if not vid:
                continue
            entry = agg.setdefault(vid, {
                "vendor_key": make_key(vid), "vendor_id": vid,
                "vendor_name": v.get("name", ""), "source": SOURCE,
                "covered_parts": [], "last_prices": [], "times": 0,
            })
            entry["covered_parts"].append(row["partNum"])
            entry["times"] += int(v.get("times") or 0)
            if v.get("lastUnitCost") is not None:
                entry["last_prices"].append(float(v["lastUnitCost"]))

    vendors = await epicor.get_vendors(agg.keys())
    out = []
    for vid, entry in agg.items():
        info = vendors.get(vid, {})
        covered = len(set(entry["covered_parts"]))
        out.append({
            "vendor_key": entry["vendor_key"],
            "vendor_id": vid,
            "vendor_name": info.get("name") or entry["vendor_name"],
            "source": SOURCE,
            "emails": info.get("emails", []),
            "has_email": bool(info.get("emails")),
            "payment_terms": info.get("terms_code", ""),
            "covered_items": covered,
            "coverage_percent": round(covered * 100 / len(part_nums), 1),
            "times_supplied": entry["times"],
            "avg_last_price": (
                round(sum(entry["last_prices"]) / len(entry["last_prices"]), 2)
                if entry["last_prices"] else None
            ),
            "po_amount": info.get("po_amount", 0),
            "reason": "เคยขายรหัสนี้ให้เรา {} รายการ".format(covered),
        })

    out.sort(key=lambda r: (-r["covered_items"], -r["times_supplied"], not r["has_email"]))
    return out[:limit]
