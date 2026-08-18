"""อ่านข้อมูลจัดซื้อจากฐานข้อมูล ``epicor_procurement``

โมดูลนี้เป็นชั้นเดียวที่แตะ collection ของ ETL (vendors / items / item_last_price /
transactions) — ที่อื่นในระบบเรียกผ่านฟังก์ชันในไฟล์นี้เท่านั้น อ่านอย่างเดียวทั้งหมด

**เรื่องการค้นหา** — ผู้ใช้จำรหัสสินค้าเป๊ะ ๆ ไม่ได้ ระบบจึงต้องหาแบบ "น่าจะใช่":

    "ethernet switch"      -> ตรงคำในคำอธิบาย
    "0101602"              -> ตรงรหัส 01-016-02-... แม้พิมพ์ไม่มีขีด
    "switch moxa"          -> ทุกคำต้องเจอ แต่เจอคนละที่ได้ (คำอธิบาย + ชื่อผู้ขาย)
    "swich"                -> สะกดผิด 1 ตัว ยังเจอ (ถอยไปหาแบบ fuzzy เมื่อผลลัพธ์ว่าง)

ทำโดยดึงผู้สมัครจาก MongoDB ด้วย regex แล้วให้คะแนนเรียงลำดับในฝั่ง Python
ที่ขนาดข้อมูลระดับ 8,600 รหัส วิธีนี้เร็วพอและคุมความหมายของ "ใกล้เคียง" ได้เอง
"""
import difflib
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.db import schema
from app.db.mongodb import get_database
from app.services import delivery

MAX_CANDIDATES = 4000       # เพดานเอกสารที่ดึงมาให้คะแนน
FUZZY_CUTOFF = 0.78         # ความใกล้เคียงขั้นต่ำตอนถอยไปหาแบบสะกดผิด

_SEP = re.compile(r"[\s\-_/.,()\[\]#]+")


# --------------------------------------------------------------------- helpers
def norm(text: Any) -> str:
    return str(text or "").strip().lower()


def compact(text: Any) -> str:
    """ตัดตัวคั่นทั้งหมดออก — ใช้เทียบรหัสสินค้าที่พิมพ์มาไม่มีขีด"""
    return _SEP.sub("", norm(text))


def tokens(q: str) -> List[str]:
    return [t for t in _SEP.split(norm(q)) if t]


def loose_code_regex(token: str) -> str:
    """รหัสสินค้าที่พิมพ์ติดกัน ให้ยอมมีตัวคั่นแทรกระหว่างอักขระได้

    "0101602" -> 0[-\\s_./]*1[-\\s_./]*0... จึงจับ "01-016-02-04-008" ได้
    """
    return r"[-\s_./]*".join(re.escape(ch) for ch in token)


def token_filter(token: str) -> Dict[str, Any]:
    """เงื่อนไข MongoDB ของคำค้นหนึ่งคำ — เจอที่ไหนก็ได้ในเอกสาร"""
    plain = {"$regex": re.escape(token), "$options": "i"}
    ors: List[Dict[str, Any]] = [
        {"partNum": plain},
        {"description": plain},
        {"vendors.name": plain},
        {"vendors.vendorId": plain},
    ]
    # คำที่เป็นรหัส (ตัวเลข/ตัวเลขปนอักษร) ให้จับแบบข้ามตัวคั่นด้วย
    if len(token) >= 3 and any(ch.isdigit() for ch in token):
        ors.append({"partNum": {"$regex": loose_code_regex(token), "$options": "i"}})
    return {"$or": ors}


def build_query(
    q: str = "",
    class_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    single_source: Optional[bool] = None,
    price_volatile: Optional[bool] = None,
    service: Optional[bool] = None,
) -> Dict[str, Any]:
    conds: List[Dict[str, Any]] = []
    for t in tokens(q):
        conds.append(token_filter(t))

    query: Dict[str, Any] = {"$and": conds} if conds else {}
    if class_id:
        query["classId"] = class_id
    if vendor_id:
        query["vendors.vendorId"] = vendor_id
    if single_source is not None:
        query["flags.singleSource"] = single_source
    if price_volatile is not None:
        query["flags.priceVolatile"] = price_volatile
    if service is not None:
        query["flags.service"] = service
    return query


def score_item(doc: Dict[str, Any], q: str, toks: List[str]) -> float:
    """ยิ่งมากยิ่งตรง — ใช้จัดอันดับผลค้นหา

    ให้น้ำหนัก: ตรงรหัสเป๊ะ > รหัสขึ้นต้นด้วยคำค้น > คำขึ้นต้นในคำอธิบาย > เจอที่ไหนก็ได้
    แล้วบวกแต้มเล็กน้อยตามมูลค่าที่เคยซื้อ เพื่อให้ของที่ใช้จริงลอยขึ้นก่อน
    """
    part = norm(doc.get("partNum"))
    part_c = compact(part)
    desc = norm(doc.get("description"))
    q_c = compact(q)
    score = 0.0

    if q_c and part_c == q_c:
        score += 1000
    elif q_c and part_c.startswith(q_c):
        score += 400
    elif q_c and q_c in part_c:
        score += 150

    if norm(q) and norm(q) in desc:
        score += 120

    for t in toks:
        if not t:
            continue
        if re.search(r"\b" + re.escape(t), desc):
            score += 40
        elif t in desc:
            score += 18
        if t in part_c:
            score += 25

    stats = doc.get("stats") or {}
    amount = float(stats.get("totalAmount") or 0)
    if amount > 0:
        score += min(amount / 1_000_000.0, 30)      # เพดาน 30 แต้ม กันของแพงมากกลบทุกอย่าง
    score += min(int(stats.get("timesOrdered") or 0), 20) * 0.5
    return score


def _fuzzy_terms(toks: List[str], vocabulary: Iterable[str]) -> List[str]:
    """หาคำในคลังที่ใกล้เคียงคำที่พิมพ์มา — ใช้เมื่อค้นแล้วไม่เจออะไรเลย"""
    vocab = sorted({w for w in vocabulary if len(w) >= 3})
    out: List[str] = []
    for t in toks:
        if len(t) < 3:
            continue
        near = difflib.get_close_matches(t, vocab, n=3, cutoff=FUZZY_CUTOFF)
        out.extend(near)
    return list(dict.fromkeys(out))


async def _vocabulary() -> List[str]:
    """คลังคำจากคำอธิบายสินค้า — ใช้เดาคำที่สะกดผิด"""
    rows = await get_database()[schema.EP_ITEMS].find({}, {"description": 1}).to_list(MAX_CANDIDATES)
    words = set()
    for r in rows:
        for w in _SEP.split(norm(r.get("description"))):
            if len(w) >= 3:
                words.add(w)
    return list(words)


# --------------------------------------------------------------------- items
ITEM_FIELDS = {
    "partNum": 1, "description": 1, "uom": 1, "classId": 1, "typeCode": 1,
    "inCatalog": 1, "stats": 1, "vendors": 1, "flags": 1, "company": 1,
}


def item_view(doc: Dict[str, Any], price: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """แปลงเอกสาร Mongo เป็นรูปแบบที่หน้าบ้านใช้ — ชื่อฟิลด์อ่านง่าย ไม่มี _id ดิบ"""
    stats = doc.get("stats") or {}
    flags = doc.get("flags") or {}
    vendors = doc.get("vendors") or []
    last = (price or {}).get("last") or {}
    lowest = (price or {}).get("lowest") or {}
    highest = (price or {}).get("highest") or {}

    return {
        "part_num": doc.get("partNum", ""),
        "description": doc.get("description") or "",
        "uom": doc.get("uom") or "",
        "class_id": doc.get("classId") or "",
        "in_catalog": bool(doc.get("inCatalog")),
        "vendor_count": int(stats.get("vendorCount") or len(vendors)),
        "times_ordered": int(stats.get("timesOrdered") or 0),
        "total_qty": stats.get("totalQty"),
        "total_amount": stats.get("totalAmount"),
        "avg_unit_cost": stats.get("avgUnitCost"),
        "min_unit_cost": stats.get("minUnitCost"),
        "max_unit_cost": stats.get("maxUnitCost"),
        "price_spread_ratio": stats.get("priceSpreadRatio"),
        "first_buy_date": stats.get("firstBuyDate"),
        "last_buy_date": stats.get("lastBuyDate"),
        "single_source": bool(flags.get("singleSource")),
        "price_volatile": bool(flags.get("priceVolatile")),
        "is_service": bool(flags.get("service")),
        "vendor_names": [v.get("name", "") for v in vendors[:4]],
        "last_price": last.get("unitCost"),
        "last_price_date": last.get("date"),
        "last_price_vendor": last.get("vendorName", ""),
        "last_price_vendor_id": last.get("vendorId", ""),
        "lowest_price": lowest.get("unitCost"),
        "highest_price": highest.get("unitCost"),
        "last_vs_lowest_pct": (price or {}).get("lastVsLowestPct"),
        "currency": ((price or {}).get("currencies") or ["THB"])[0],
        "multi_currency": bool((price or {}).get("multiCurrency")),
        "has_price": bool(last.get("unitCost")),
    }


async def prices_for(part_nums: List[str]) -> Dict[str, Dict[str, Any]]:
    if not part_nums:
        return {}
    rows = await get_database()[schema.EP_LAST_PRICE].find(
        {"partNum": {"$in": part_nums}}
    ).to_list(len(part_nums))
    return {r["partNum"]: r for r in rows}


SORTS = {
    "relevance": None,
    "amount": ("stats.totalAmount", -1),
    "recent": ("stats.lastBuyDate", -1),
    "times": ("stats.timesOrdered", -1),
    "part": ("partNum", 1),
    "spread": ("stats.priceSpreadRatio", -1),
}


async def search_items(
    q: str = "",
    class_id: Optional[str] = None,
    vendor_id: Optional[str] = None,
    single_source: Optional[bool] = None,
    price_volatile: Optional[bool] = None,
    service: Optional[bool] = None,
    has_price: Optional[bool] = None,
    sort: str = "relevance",
    skip: int = 0,
    limit: int = 40,
) -> Dict[str, Any]:
    """ค้นหาสินค้าแบบ "น่าจะใช่" แล้วแนบราคาล่าสุดให้ทุกแถว

    ไม่ใส่คำค้น = เห็นรายการสินค้าทันที เรียงตามมูลค่าที่เคยซื้อ
    """
    db = get_database()
    col = db[schema.EP_ITEMS]
    toks = tokens(q)
    query = build_query(q, class_id, vendor_id, single_source, price_volatile, service)

    fuzzy_used: List[str] = []
    docs: List[Dict[str, Any]] = []

    if toks:
        docs = await col.find(query, ITEM_FIELDS).to_list(MAX_CANDIDATES)
        if not docs:
            # ไม่เจอเลย → เดาว่าพิมพ์ผิด ลองหาคำที่ใกล้เคียงในคลังคำอธิบาย
            fuzzy_used = _fuzzy_terms(toks, await _vocabulary())
            if fuzzy_used:
                alt = build_query(" ".join(fuzzy_used), class_id, vendor_id,
                                  single_source, price_volatile, service)
                docs = await col.find(alt, ITEM_FIELDS).to_list(MAX_CANDIDATES)

        if sort == "relevance":
            scored: List[Tuple[float, Dict[str, Any]]] = [
                (score_item(d, q, toks or fuzzy_used), d) for d in docs
            ]
            scored.sort(key=lambda pair: (-pair[0], pair[1].get("partNum", "")))
            docs = [d for _, d in scored]
        else:
            field, direction = SORTS.get(sort) or SORTS["amount"]
            docs.sort(key=lambda d: _sort_key(d, field), reverse=direction < 0)

        total = len(docs)
        page = docs[skip:skip + limit]
    else:
        field, direction = SORTS.get(sort) or SORTS["amount"]
        if sort == "relevance":
            field, direction = SORTS["amount"]
        total = await col.count_documents(query)
        page = await col.find(query, ITEM_FIELDS).sort(field, direction) \
            .skip(skip).limit(limit).to_list(limit)

    prices = await prices_for([d.get("partNum", "") for d in page])
    items = [item_view(d, prices.get(d.get("partNum", ""))) for d in page]

    if has_price is not None:
        items = [i for i in items if i["has_price"] is has_price]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + len(page) < total,
        "items": items,
        "fuzzy_terms": fuzzy_used,
    }


def _sort_key(doc: Dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        cur = (cur or {}).get(part) if isinstance(cur, dict) else None
    if cur is None:
        return ""
    return cur


async def get_item(part_num: str) -> Optional[Dict[str, Any]]:
    """สินค้า 1 รหัส พร้อมราคาล่าสุด/ต่ำสุด/สูงสุด และผู้ขายทุกรายที่เคยขาย"""
    db = get_database()
    doc = await db[schema.EP_ITEMS].find_one({"partNum": part_num})
    price = await db[schema.EP_LAST_PRICE].find_one({"partNum": part_num})
    if not doc and not price:
        return None
    doc = doc or {"partNum": part_num, "description": (price or {}).get("description", "")}

    view = item_view(doc, price)
    view["price"] = _price_block(price)
    view["vendors"] = _item_vendors(doc, price)
    return view


def _price_block(price: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not price:
        return None

    def point(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not p:
            return None
        return {
            "unit_cost": p.get("unitCost"),
            "date": p.get("date"),
            "qty": p.get("qty"),
            "currency": p.get("currency") or "THB",
            "po_num": p.get("poNum"),
            "po_line": p.get("poLine"),
            "vendor_id": p.get("vendorId", ""),
            "vendor_name": p.get("vendorName", ""),
        }

    return {
        "last": point(price.get("last")),
        "lowest": point(price.get("lowest")),
        "highest": point(price.get("highest")),
        "priced_times": price.get("pricedTimes"),
        "vendor_count": price.get("vendorCount"),
        "avg_unit_cost": price.get("avgUnitCost"),
        "spread_ratio": price.get("spreadRatio"),
        "last_vs_lowest_pct": price.get("lastVsLowestPct"),
        "last_vs_highest_pct": price.get("lastVsHighestPct"),
        "currencies": price.get("currencies") or ["THB"],
        "multi_currency": bool(price.get("multiCurrency")),
        "single_source": bool(price.get("singleSource")),
    }


def _item_vendors(doc: Dict[str, Any], price: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """รวมผู้ขายจาก items.vendors (มุมมองสะสม) กับ item_last_price.vendors (มุมมองราคา)"""
    by_id: Dict[str, Dict[str, Any]] = {}

    for v in doc.get("vendors") or []:
        vid = str(v.get("vendorId") or v.get("vendorNum") or "")
        by_id[vid] = {
            "vendor_id": vid,
            "vendor_num": v.get("vendorNum"),
            "vendor_key": "epicor:{}".format(vid),
            "name": v.get("name", ""),
            "times": v.get("times", 0),
            "qty": v.get("qty"),
            "amount": v.get("amount"),
            "min_unit_cost": v.get("minUnitCost"),
            "max_unit_cost": v.get("maxUnitCost"),
            "avg_unit_cost": v.get("avgUnitCost"),
            "last_buy_date": v.get("lastBuyDate"),
            "last_unit_cost": None,
            "last_po_num": None,
            "currency": "THB",
        }

    for v in (price or {}).get("vendors") or []:
        vid = str(v.get("vendorId") or v.get("vendorNum") or "")
        row = by_id.setdefault(vid, {
            "vendor_id": vid, "vendor_num": v.get("vendorNum"),
            "vendor_key": "epicor:{}".format(vid), "name": v.get("name", ""),
            "times": v.get("times", 0), "qty": None, "amount": None,
            "min_unit_cost": None, "max_unit_cost": None, "avg_unit_cost": None,
            "last_buy_date": None,
        })
        row["last_unit_cost"] = v.get("lastUnitCost")
        row["last_po_num"] = v.get("lastPoNum")
        row["last_buy_date"] = v.get("lastDate") or row.get("last_buy_date")
        row["currency"] = v.get("currency") or "THB"
        for src, dst in (("minUnitCost", "min_unit_cost"), ("maxUnitCost", "max_unit_cost"),
                         ("avgUnitCost", "avg_unit_cost")):
            if row.get(dst) is None:
                row[dst] = v.get(src)

    rows = list(by_id.values())
    # เรียงจากราคาล่าสุดถูกสุดก่อน — คนซื้อมองหา "ควรขอราคาจากใคร"
    rows.sort(key=lambda r: (
        r.get("last_unit_cost") is None,
        r.get("last_unit_cost") if r.get("last_unit_cost") is not None else 0,
    ))
    return rows


# --------------------------------------------------------------- transactions
def transaction_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    ref = doc.get("ref") or {}
    meta = doc.get("meta") or {}
    vendor = doc.get("vendor") or {}
    part = doc.get("part") or {}
    return {
        "id": str(doc.get("_id", "")),
        "doc_type": doc.get("docType", ""),
        "doc_type_label": schema.DOC_TYPE_LABEL.get(doc.get("docType", ""), doc.get("docType", "")),
        "date": doc.get("date"),
        "vendor_id": str(vendor.get("id") or ""),
        "vendor_num": vendor.get("num"),
        "vendor_key": "epicor:{}".format(vendor.get("id") or ""),
        "vendor_name": vendor.get("name", ""),
        "part_num": part.get("num", ""),
        "part_description": part.get("description", ""),
        "uom": part.get("uom", ""),
        "qty": doc.get("qty"),
        "unit_cost": doc.get("unitCost"),
        "amount": doc.get("amount"),
        "currency": doc.get("currency") or "THB",
        "po_num": ref.get("poNum"),
        "po_line": ref.get("poLine"),
        "pack_slip": ref.get("packSlip"),
        "invoice_num": ref.get("invoiceNum"),
        "buyer_id": meta.get("buyerId", ""),
        "due_date": meta.get("dueDate"),
        "open_line": bool(meta.get("openLine")),
    }


async def transactions(
    part_num: Optional[str] = None,
    vendor_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """รายการเคลื่อนไหวจริง — ใช้ทั้งในหน้าสินค้าและหน้าผู้ขาย"""
    query: Dict[str, Any] = {}
    if part_num:
        query["part.num"] = part_num
    if vendor_id:
        query["vendor.id"] = vendor_id
    if doc_type:
        query["docType"] = doc_type

    col = get_database()[schema.EP_TRANSACTIONS]
    total = await col.count_documents(query)
    rows = await col.find(query).sort("date", -1).skip(skip).limit(limit).to_list(limit)
    return {
        "total": total, "skip": skip, "limit": limit,
        "has_more": skip + len(rows) < total,
        "items": [transaction_view(r) for r in rows],
    }


async def transaction_summary(
    part_num: Optional[str] = None, vendor_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """สรุปจำนวน/มูลค่าแยกตามชนิดเอกสาร (สั่งซื้อ / รับของ / วางบิล)"""
    query: Dict[str, Any] = {}
    if part_num:
        query["part.num"] = part_num
    if vendor_id:
        query["vendor.id"] = vendor_id

    col = get_database()[schema.EP_TRANSACTIONS]
    buckets: Dict[str, Dict[str, Any]] = {}
    async for row in col.find(query, {"docType": 1, "qty": 1, "amount": 1, "date": 1}):
        b = buckets.setdefault(row.get("docType", ""), {
            "doc_type": row.get("docType", ""),
            "doc_type_label": schema.DOC_TYPE_LABEL.get(row.get("docType", ""), ""),
            "lines": 0, "qty": 0.0, "amount": 0.0, "last_date": None,
        })
        b["lines"] += 1
        b["qty"] += float(row.get("qty") or 0)
        b["amount"] += float(row.get("amount") or 0)
        date = row.get("date")
        if date and (b["last_date"] is None or date > b["last_date"]):
            b["last_date"] = date

    order = [schema.DOC_PO, schema.DOC_RECEIPT, schema.DOC_INVOICE]
    rows = sorted(buckets.values(),
                  key=lambda b: order.index(b["doc_type"]) if b["doc_type"] in order else 99)
    for r in rows:
        r["qty"] = round(r["qty"], 4)
        r["amount"] = round(r["amount"], 2)
    return rows


async def price_history(part_num: str, limit: int = 200) -> List[Dict[str, Any]]:
    """ทุกครั้งที่เคยสั่งซื้อรหัสนี้ เรียงตามเวลา — ใช้วาดกราฟราคา"""
    rows = await get_database()[schema.EP_TRANSACTIONS].find(
        {"part.num": part_num, "docType": schema.DOC_PO}
    ).to_list(limit)
    out = []
    for r in rows:
        if not r.get("unitCost"):
            continue
        out.append({
            "date": r.get("date"),
            "unit_cost": r.get("unitCost"),
            "qty": r.get("qty"),
            "amount": r.get("amount"),
            "vendor_id": str((r.get("vendor") or {}).get("id") or ""),
            "vendor_name": (r.get("vendor") or {}).get("name", ""),
            "po_num": (r.get("ref") or {}).get("poNum"),
        })
    out.sort(key=lambda r: (r["date"] is None, r["date"]))
    return out


# --------------------------------------------------------------------- vendors
PLACEHOLDER_VALUES = {"-", "--", "n/a", "na", "none", ".", "x"}


def _clean_contact_value(value: Any) -> str:
    """Epicor ใส่ '-' หรือ 'N/A' แทนค่าว่างบ่อย ๆ — ถือว่าไม่มีข้อมูล"""
    text = str(value or "").strip()
    return "" if text.lower() in PLACEHOLDER_VALUES else text


def build_contacts(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """รวมผู้ติดต่อของผู้ขายให้ครบทุกแหล่ง

    Epicor เก็บช่องทางติดต่อไว้สองที่ และหลายรายมีแค่ที่เดียว:

    * ``contacts``  รายบุคคล มาจาก Erp.VendCnt — มีไม่ครบทุกผู้ขาย
    * ``contact``   อีเมล/เบอร์ของบริษัท อยู่บนทะเบียนผู้ขายเอง

    ถ้าอ่านแค่ ``contacts`` ผู้ขายที่มีแต่อีเมลบริษัทจะกลายเป็น "ไม่มีผู้ติดต่อ"
    ทั้งที่ติดต่อได้จริง จึงเติมช่องทางระดับบริษัทเข้าไปเป็นอีกรายการหนึ่ง
    โดยติดธง ``is_company`` ไว้ให้หน้าบ้านบอกผู้ใช้ได้ว่านี่ไม่ใช่ชื่อคน
    """
    rows: List[Dict[str, Any]] = []
    seen_emails = set()

    for c in doc.get("contacts") or []:
        email = _clean_contact_value(c.get("email"))
        phone = _clean_contact_value(c.get("phone"))
        name = _clean_contact_value(c.get("name"))
        if not (email or phone or name):
            continue
        rows.append({
            "name": name,
            "email": email,
            "phone": phone,
            "function": _clean_contact_value(c.get("function")),
            "is_company": False,
        })
        if email:
            seen_emails.add(email.lower())

    company = doc.get("contact") or {}
    c_email = _clean_contact_value(company.get("email"))
    c_phone = _clean_contact_value(company.get("phone"))
    if (c_email and c_email.lower() not in seen_emails) or (c_phone and not rows):
        rows.append({
            "name": doc.get("name", "") or "ช่องทางติดต่อของบริษัท",
            "email": c_email,
            "phone": c_phone,
            "function": "ติดต่อบริษัท",
            "is_company": True,
        })

    # รายที่มีอีเมลจริงควรถูกใช้เป็นผู้ติดต่อหลัก เพราะ RFQ ส่งทางอีเมล
    rows.sort(key=lambda r: (not r["email"], r["is_company"]))
    for i, row in enumerate(rows):
        row["is_primary"] = i == 0
    return rows


def vendor_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    stats = doc.get("stats") or {}
    po = stats.get("po") or {}
    invoice = stats.get("invoice") or {}
    receipt = stats.get("receipt") or {}
    address = doc.get("address") or {}

    contacts = build_contacts(doc)
    emails = list(dict.fromkeys(c["email"] for c in contacts if c["email"]))
    phones = list(dict.fromkeys(c["phone"] for c in contacts if c["phone"]))

    vendor_id = str(doc.get("vendorId") or doc.get("vendorNum") or "")
    return {
        "vendor_key": "epicor:{}".format(vendor_id),
        "vendor_id": vendor_id,
        "vendor_num": doc.get("vendorNum"),
        "name": doc.get("name", ""),
        "address": {
            "line1": address.get("line1", ""), "line2": address.get("line2", ""),
            "city": address.get("city", ""), "state": address.get("state", ""),
            "zip": address.get("zip", ""), "country": address.get("country", ""),
        },
        "emails": emails,
        "phones": phones,
        "contacts": contacts,
        "contact_count": len(contacts),
        "currency": doc.get("currency") or "THB",
        "terms_code": doc.get("termsCode", ""),
        "group_code": doc.get("groupCode", ""),
        "tax_id": doc.get("taxId", ""),
        "inactive": bool(doc.get("inactive")),
        "has_purchase": bool(doc.get("hasPurchase")),
        "po_count": po.get("count", 0),
        "po_lines": po.get("lineCount", 0),
        "po_amount": po.get("amount", 0),
        "distinct_parts": po.get("distinctParts", 0),
        "first_buy_date": po.get("firstDate"),
        "last_buy_date": po.get("lastDate"),
        "invoice_amount": invoice.get("amount", 0),
        "invoice_count": invoice.get("invoiceCount", 0),
        "receipt_count": receipt.get("count", 0),
        "receipt_last_date": receipt.get("lastDate"),
        "top_parts": [
            {"part_num": p.get("partNum", ""), "times": p.get("times", 0),
             "qty": p.get("qty"), "amount": p.get("amount")}
            for p in (stats.get("topParts") or [])
        ],
        "has_email": bool(emails),
    }


VENDOR_SORTS = {
    "amount": ("stats.po.amount", -1),
    "name": ("name", 1),
    "recent": ("stats.po.lastDate", -1),
    "parts": ("stats.po.distinctParts", -1),
}


async def search_vendors(
    q: str = "",
    has_purchase: Optional[bool] = None,
    has_email: Optional[bool] = None,
    active_only: bool = False,
    sort: str = "amount",
    skip: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    col = get_database()[schema.EP_VENDORS]
    query: Dict[str, Any] = {}
    conds = []
    for t in tokens(q):
        rx = {"$regex": re.escape(t), "$options": "i"}
        conds.append({"$or": [
            {"name": rx}, {"vendorId": rx}, {"taxId": rx},
            {"contacts.name": rx}, {"contacts.email": rx}, {"contact.email": rx},
        ]})
    if conds:
        query["$and"] = conds
    if has_purchase is not None:
        query["hasPurchase"] = has_purchase
    if active_only:
        query["inactive"] = False

    field, direction = VENDOR_SORTS.get(sort) or VENDOR_SORTS["amount"]
    total = await col.count_documents(query)
    rows = await col.find(query).sort(field, direction).skip(skip).limit(limit).to_list(limit)
    items = [vendor_view(r) for r in rows]
    if has_email is not None:
        items = [v for v in items if v["has_email"] is has_email]

    return {
        "total": total, "skip": skip, "limit": limit,
        "has_more": skip + len(rows) < total, "items": items,
    }


async def enrich_top_parts(vendors: Iterable[Dict[str, Any]]) -> None:
    """เติมชื่อสินค้าให้ ``top_parts`` ของผู้ขาย (แก้ไขในที่)

    ``vendors.stats.topParts`` ที่ ETL สร้างไว้เก็บแค่รหัสสินค้า เพราะสรุปมาจาก
    บรรทัด PO ล้วน ๆ — คนอ่านรหัสอย่างเดียวไม่รู้ว่าคืออะไร จึงไปดึงคำอธิบาย
    จาก ``items`` มาแปะให้ตอนอ่าน (ไม่แตะเอกสารของ ETL)

    ทำเฉพาะตอนเปิดหน้ารายละเอียดผู้ขาย ไม่ทำในหน้ารายการ เพื่อไม่ให้ยิงคิวรีเกินจำเป็น
    """
    rows = [p for v in vendors for p in (v.get("top_parts") or [])]
    part_nums = [p["part_num"] for p in rows if p.get("part_num")]
    if not part_nums:
        return

    docs = await get_database()[schema.EP_ITEMS].find(
        {"partNum": {"$in": list(dict.fromkeys(part_nums))}},
        {"partNum": 1, "description": 1, "uom": 1, "classId": 1},
    ).to_list(len(part_nums))
    by_part = {d["partNum"]: d for d in docs}

    for row in rows:
        info = by_part.get(row.get("part_num")) or {}
        # ถ้าไม่มีในทะเบียนสินค้า ให้ใช้รหัสไปก่อน จะได้ไม่มีช่องว่างในตาราง
        row["description"] = info.get("description") or row.get("part_num", "")
        row["uom"] = info.get("uom") or ""
        row["class_id"] = info.get("classId") or ""
        row["in_catalog"] = bool(info)


async def get_vendor(vendor_id: str) -> Optional[Dict[str, Any]]:
    col = get_database()[schema.EP_VENDORS]
    doc = await col.find_one({"vendorId": str(vendor_id)})
    if not doc and str(vendor_id).isdigit():
        doc = await col.find_one({"vendorNum": int(vendor_id)})
    if not doc:
        return None
    view = vendor_view(doc)
    await enrich_top_parts([view])
    return view


async def get_vendors(vendor_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    ids = [str(v) for v in dict.fromkeys(vendor_ids) if str(v)]
    if not ids:
        return {}
    rows = await get_database()[schema.EP_VENDORS].find(
        {"vendorId": {"$in": ids}}
    ).to_list(len(ids))
    return {v["vendor_id"]: v for v in (vendor_view(r) for r in rows)}


async def vendor_items(
    vendor_id: str, q: str = "", skip: int = 0, limit: int = 50
) -> Dict[str, Any]:
    """สินค้าที่ผู้ขายรายนี้เคยขายให้ พร้อมราคาล่าสุดของ *รายนี้* (ไม่ใช่ราคาต่ำสุดรวม)"""
    result = await search_items(q=q, vendor_id=str(vendor_id), sort="amount",
                                skip=skip, limit=limit)
    part_nums = [i["part_num"] for i in result["items"]]
    prices = await prices_for(part_nums)

    for row in result["items"]:
        mine = None
        for v in (prices.get(row["part_num"]) or {}).get("vendors") or []:
            if str(v.get("vendorId")) == str(vendor_id):
                mine = v
                break
        row["vendor_last_price"] = (mine or {}).get("lastUnitCost")
        row["vendor_last_date"] = (mine or {}).get("lastDate")
        row["vendor_times"] = (mine or {}).get("times")
    return result


# --------------------------------------------------------------------- misc
async def facets() -> Dict[str, Any]:
    """ตัวเลือกสำหรับตัวกรอง + จำนวนข้อมูลทั้งหมด"""
    db = get_database()
    classes = await db[schema.EP_ITEMS].distinct("classId")
    run = await db[schema.EP_RUNS].find_one(sort=[("finishedAt", -1)])
    return {
        "class_ids": sorted([c for c in classes if c]),
        "doc_types": [
            {"value": k, "label": v} for k, v in schema.DOC_TYPE_LABEL.items()
        ],
        "counts": await counts(),
        "last_etl": {
            "finished_at": (run or {}).get("finishedAt"),
            "mode": (run or {}).get("mode", ""),
        } if run else None,
    }


async def counts() -> Dict[str, int]:
    db = get_database()
    out = {}
    for name in schema.EPICOR_COLLECTIONS:
        try:
            out[name] = await db[name].count_documents({})
        except Exception:
            out[name] = -1
    return out


async def overview() -> Dict[str, Any]:
    """ตัวเลขสรุปสำหรับหน้าภาพรวม"""
    db = get_database()
    c = await counts()
    top_items = await db[schema.EP_ITEMS].find({}, ITEM_FIELDS) \
        .sort("stats.totalAmount", -1).limit(8).to_list(8)
    top_vendors = await db[schema.EP_VENDORS].find({"hasPurchase": True}) \
        .sort("stats.po.amount", -1).limit(8).to_list(8)
    volatile = await db[schema.EP_ITEMS].find(
        {"flags.priceVolatile": True, "flags.service": False}, ITEM_FIELDS
    ).sort("stats.priceSpreadRatio", -1).limit(8).to_list(8)

    prices = await prices_for([d.get("partNum", "") for d in top_items + volatile])
    return {
        "counts": {
            "vendors": c.get(schema.EP_VENDORS, 0),
            "items": c.get(schema.EP_ITEMS, 0),
            "transactions": c.get(schema.EP_TRANSACTIONS, 0),
            "priced_items": c.get(schema.EP_LAST_PRICE, 0),
        },
        "top_items": [item_view(d, prices.get(d.get("partNum", ""))) for d in top_items],
        "top_vendors": [vendor_view(d) for d in top_vendors],
        "price_volatile": [item_view(d, prices.get(d.get("partNum", ""))) for d in volatile],
        "by_doc_type": await transaction_summary(),
        "delivery": await delivery.company_summary(),
    }


# ------------------------------------------------------------ ภาพรวมเชิงกลยุทธ์
# สองฟังก์ชันล่างตอบคำถามระดับ "ทั้งพอร์ต" ซึ่งต่างจากที่เหลือในไฟล์นี้ที่ตอบ
# ทีละรายการ · ทั้งคู่ต้องกวาดข้อมูลทั้งฐานจึงถูกเรียกผ่าน snapshot เท่านั้น
# ไม่ใช่เรียกสดทุกครั้งที่เปิดหน้า (ดู services/snapshot.py)

def _dig(doc: Dict[str, Any], dotted: str) -> Any:
    """อ่านฟิลด์ซ้อนด้วยเส้นทางแบบจุด เช่น "stats.po.amount" — ไม่มีก็คืน None"""
    cur: Any = doc
    for part in dotted.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


async def pareto() -> Dict[str, Any]:
    """เงินกระจุกตัวที่สินค้า/ผู้ขายกี่รายแรก

    ตอบคำถามที่ตาราง "8 อันดับแรก" ตอบไม่ได้: ควรเอาแรงไปลงกับกี่รหัสจึงคุมงบได้
    คืนเส้นสะสมแบบย่อจุดแล้ว (ไม่ส่ง 8,620 จุดไปให้เบราว์เซอร์วาด) พร้อมจุดตัด
    ที่ใช้ตัดสินใจจริงคือ 50/80/90%
    """
    db = get_database()

    async def _curve(coll: str, amount_field: str, match: Dict[str, Any]) -> Dict[str, Any]:
        amounts = [
            _dig(d, amount_field) or 0
            async for d in db[coll].find(match, {amount_field: 1}).sort(amount_field, -1)
        ]
        amounts = [a for a in amounts if a > 0]
        total = sum(amounts)
        n = len(amounts)
        if not total:
            return {"total": 0.0, "count": 0, "points": [], "thresholds": {}}

        # ย่อจุด: ช่วงต้นเก็บละเอียดเพราะเป็นช่วงที่เส้นชันและเป็นคำตอบของคำถาม
        # ช่วงท้ายเก็บหยาบได้เพราะแบนแล้ว — ถ้าย่อแบบเว้นระยะเท่ากันจะกินหัวโค้งหาย
        marks = sorted({
            *range(0, min(n, 50) + 1, 5),
            *range(50, min(n, 500) + 1, 25),
            *range(500, min(n, 2000) + 1, 150),
            *range(2000, n + 1, max(1, n // 20)),
            n,
        })
        run, points, idx = 0.0, [], 0
        for i, a in enumerate(amounts, start=1):
            run += a
            if idx < len(marks) and i >= marks[idx]:
                points.append({"n": i, "pct": round(run / total * 100, 2)})
                while idx < len(marks) and marks[idx] <= i:
                    idx += 1

        thresholds, run = {}, 0.0
        want = [(50, "p50"), (80, "p80"), (90, "p90")]
        for i, a in enumerate(amounts, start=1):
            run += a
            while want and run / total * 100 >= want[0][0]:
                thresholds[want[0][1]] = {"n": i, "share_of_catalog": round(i / n * 100, 2)}
                want.pop(0)
            if not want:
                break
        return {"total": total, "count": n, "points": points, "thresholds": thresholds}

    return {
        "items": await _curve(schema.EP_ITEMS, "stats.totalAmount", {}),
        "vendors": await _curve(schema.EP_VENDORS, "stats.po.amount", {"hasPurchase": True}),
    }


async def spend_trend() -> Dict[str, Any]:
    """มูลค่าซื้อและจำนวนผู้ขายรายปี — แนวโน้มตามเวลาที่ยังไม่มีหน้าไหนแสดง

    นับจากบรรทัดใบสั่งซื้อเท่านั้น (ไม่รวมรับของ/ใบแจ้งหนี้) เพราะเป็นตัวแทนของ
    "การตัดสินใจซื้อ" ซึ่งเป็นสิ่งที่ฝ่ายจัดซื้อควบคุมได้จริง
    """
    db = get_database()
    rows = await db[schema.EP_TRANSACTIONS].aggregate([
        {"$match": {"docType": schema.DOC_PO, "date": {"$ne": None}}},
        {"$group": {
            "_id": {"$year": "$date"},
            "amount": {"$sum": "$amount"},
            "lines": {"$sum": 1},
            "vendors": {"$addToSet": "$vendor.id"},
            "parts": {"$addToSet": "$part.num"},
        }},
        {"$sort": {"_id": 1}},
    ]).to_list(60)

    years = [
        {
            "year": r["_id"],
            "amount": r["amount"] or 0,
            "lines": r["lines"],
            "vendors": len(r.get("vendors") or []),
            "parts": len(r.get("parts") or []),
        }
        for r in rows if r.get("_id")
    ]
    # ปีสุดท้ายมักยังไม่ครบปี — ติดธงไว้ให้หน้าบ้านแสดงต่างจากปีที่จบแล้ว
    latest = await db[schema.EP_TRANSACTIONS].find_one(
        {"docType": schema.DOC_PO, "date": {"$ne": None}}, {"date": 1}, sort=[("date", -1)]
    )
    last_date = latest.get("date") if latest else None
    if years and last_date is not None:
        years[-1]["partial"] = years[-1]["year"] == last_date.year

    return {"years": years, "last_po_date": last_date}
