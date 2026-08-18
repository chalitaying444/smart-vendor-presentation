"""ประมาณราคา BOM — เอารายการของโครงการมาจับคู่กับสินค้าที่เคยซื้อจริง

หลักคิดสามข้อที่ยึดตลอดไฟล์นี้:

1. **จับคู่ผิดแย่กว่าจับคู่ไม่ได้** — ถ้าคะแนนความมั่นใจต่ำกว่าเกณฑ์ จะปล่อยว่าง
   แล้วบอกให้คนเลือกเอง ดีกว่าเดามั่วแล้วให้ตัวเลขงบที่ดูน่าเชื่อถือแต่ผิด
2. **ยอดรวมต้องบอกด้วยว่าครอบคลุมแค่ไหน** — ถ้ามี 40 รายการแต่ตีราคาได้ 25
   ยอดรวมเฉย ๆ คือการโกหก จึงต้องส่ง coverage กลับไปเสมอ
3. **ราคาเก่ามีวันหมดอายุ** — ราคาล่าสุดเมื่อ 3 ปีก่อนไม่ใช่ "ราคาปัจจุบัน"
   จึงติดธงบอกอายุราคาไว้ทุกบรรทัด
"""
import csv
import io
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from app.db import schema
from app.db.mongodb import get_database
from app.models.common import utcnow
from app.services import delivery, epicor

# ---------------------------------------------------------------- ค่าคงที่
MATCH_FLOOR = 0.34          # ต่ำกว่านี้ = ไม่จับคู่ให้ ปล่อยให้คนเลือกเอง
CONFIDENT = 0.72            # ตั้งแต่นี้ = มั่นใจสูง
MAYBE = 0.48                # ตั้งแต่นี้ = พอไปได้ แต่ควรกดดูสักหน่อย
STALE_DAYS = 365            # ราคาเก่ากว่านี้ = เตือนว่าอาจไม่ใช่ราคาปัจจุบันแล้ว
MAX_CANDIDATES = 3000
TOP_CANDIDATES = 8
MAX_LINES = 500

# คำที่ไม่ช่วยแยกแยะสินค้า ตัดทิ้งก่อนจับคู่
STOPWORDS = {
    "ชุด", "อัน", "ตัว", "เส้น", "แผ่น", "ชิ้น", "ราคา", "งาน", "ค่า", "รายการ",
    "the", "and", "for", "with", "of", "set", "pcs", "pc", "ea", "each", "no",
}
UNIT_WORDS = {
    "ea", "pcs", "pc", "set", "lot", "m", "mm", "cm", "km", "kg", "g", "l",
    "roll", "box", "pack", "unit", "อัน", "ชุด", "เส้น", "ตัว", "ม.", "เมตร",
    "ชิ้น", "กล่อง", "ม้วน", "แผ่น", "ถุง", "กก.", "ตร.ม.",
}

_NUM = re.compile(r"^-?[\d,]+(\.\d+)?$")
_SPLIT = re.compile(r"[\t;|]|,(?![^()]*\))")

# หัวคอลัมน์ที่พบบ่อยใน BOM ของจริง
HEAD_NAME = ("รายการ", "ชื่อ", "รายละเอียด", "description", "item", "name",
             "spec", "material", "วัสดุ", "อุปกรณ์")
HEAD_QTY = ("จำนวน", "ปริมาณ", "qty", "quantity", "amount", "จน.")
HEAD_UOM = ("หน่วย", "uom", "unit")
HEAD_PART = ("รหัส", "part", "code", "sku", "partnum", "รหัสสินค้า")


# ---------------------------------------------------------------- อ่าน BOM เข้ามา
def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).strip()


def _as_qty(value: Any) -> Optional[float]:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        qty = float(text)
    except ValueError:
        return None
    return qty if qty > 0 else None


def _header_map(cells: List[str]) -> Optional[Dict[str, int]]:
    """ถ้าแถวนี้หน้าตาเป็นหัวตาราง คืนตำแหน่งคอลัมน์ที่เจอ"""
    low = [_clean(c).lower() for c in cells]
    found: Dict[str, int] = {}
    for idx, cell in enumerate(low):
        if not cell:
            continue
        if "name" not in found and any(k in cell for k in HEAD_NAME):
            found["name"] = idx
        elif "qty" not in found and any(k in cell for k in HEAD_QTY):
            found["qty"] = idx
        elif "uom" not in found and any(k in cell for k in HEAD_UOM):
            found["uom"] = idx
        elif "part" not in found and any(k in cell for k in HEAD_PART):
            found["part"] = idx
    return found if "name" in found and len(found) >= 2 else None


def _row_to_line(cells: List[str], cols: Optional[Dict[str, int]]) -> Optional[Dict[str, Any]]:
    cells = [_clean(c) for c in cells]
    if not any(cells):
        return None

    if cols:
        name = cells[cols["name"]] if cols["name"] < len(cells) else ""
        qty = _as_qty(cells[cols["qty"]]) if "qty" in cols and cols["qty"] < len(cells) else None
        uom = cells[cols["uom"]] if "uom" in cols and cols["uom"] < len(cells) else ""
        part = cells[cols["part"]] if "part" in cols and cols["part"] < len(cells) else ""
        # แถวที่มีแต่ข้อความในช่องชื่อ ไม่มีจำนวน ไม่มีหน่วย ไม่มีรหัส = หัวข้อหมวด
        # ไม่ใช่รายการของ · ถ้าปล่อยผ่านแล้วเดาจำนวนให้เป็น 1 จะได้บรรทัดขยะ
        # ที่ดูเหมือนของจริงปนอยู่ในงบ
        if qty is None and not uom and not part:
            return None
    else:
        # ไม่มีหัวตาราง — เดาจากรูปแบบ: ข้อความยาวสุดคือชื่อ ตัวเลขท้าย ๆ คือจำนวน
        texts = [c for c in cells if c and not _NUM.match(c)]
        nums = [c for c in cells if c and _NUM.match(c)]
        # ตัดเลขลำดับหน้าแถวทิ้ง (1. 2. 3.) ไม่ใช่จำนวน
        if nums and cells and cells[0] == nums[0] and len(cells) > 2:
            nums = nums[1:]
        name = max(texts, key=len) if texts else ""
        qty = _as_qty(nums[0]) if nums else None
        uom = ""
        part = ""
        for text in texts:
            if text != name and _clean(text).lower() in UNIT_WORDS:
                uom = text
        for text in texts:
            if text != name and re.match(r"^[\w]{2,}(-[\w]+){2,}$", text):
                part = text

    name = _clean(name)
    if not name or _NUM.match(name):
        return None
    return {"name": name[:300], "qty": qty or 1.0, "uom": _clean(uom)[:20],
            "part_hint": _clean(part)[:60], "remark": ""}


def parse_text(text: str) -> List[Dict[str, Any]]:
    """อ่าน BOM ที่วางมาจาก Excel — คั่นด้วย tab / , / ; / | หรือช่องว่างยาว ๆ

    ถ้ามี tab ให้ตัดด้วย tab อย่างเดียว ห้ามตัดด้วยลูกน้ำซ้ำ —
    คัดลอกจาก Excel มาจะเป็น tab เสมอ และตัวเลขไทยใส่ลูกน้ำคั่นหลักพัน
    ("1,200") ถ้าตัดด้วยลูกน้ำด้วยจะกลายเป็นจำนวน 1 กับหน่วย "200"
    """
    rows: List[List[str]] = []
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        if "\t" in raw:
            cells = raw.split("\t")
        elif ";" in raw or "|" in raw or "," in raw:
            cells = _SPLIT.split(raw)
        elif re.search(r"\s{2,}", raw):
            cells = re.split(r"\s{2,}", raw)
        else:
            cells = [raw]
        rows.append([_clean(c) for c in cells])
    return _rows_to_lines(rows)


def parse_csv(data: bytes) -> List[Dict[str, Any]]:
    for encoding in ("utf-8-sig", "cp874", "utf-8", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", "ignore")
    try:
        dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
        reader = csv.reader(io.StringIO(text), dialect)
    except csv.Error:
        reader = csv.reader(io.StringIO(text))
    return _rows_to_lines([[_clean(c) for c in row] for row in reader])


def parse_xlsx(data: bytes) -> List[Dict[str, Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    rows: List[List[str]] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            rows.append([_clean(c) for c in (row or [])])
        if rows:
            break       # ใช้ชีตแรกที่มีข้อมูล
    workbook.close()
    return _rows_to_lines(rows)


def _rows_to_lines(rows: List[List[str]]) -> List[Dict[str, Any]]:
    """หาหัวตารางให้เจอก่อน แล้วค่อยอ่านรายการ

    ต้องสแกนหาหัวตารางให้จบก่อนเริ่มเก็บ ไม่ใช่เก็บไปหาไป —
    BOM จริงมักมีชื่อโครงการ/ผู้จัดทำ/วันที่ อยู่เหนือหัวตาราง
    ถ้าอ่านไปด้วยหาไปด้วย บรรทัดพวกนั้นจะกลายเป็นรายการของที่ต้องซื้อ
    """
    start, cols = 0, None
    for index, cells in enumerate(rows):
        header = _header_map(cells)
        if header:
            cols, start = header, index + 1
            break

    lines: List[Dict[str, Any]] = []
    for cells in rows[start:]:
        line = _row_to_line(cells, cols)
        if line:
            lines.append(line)
        if len(lines) >= MAX_LINES:
            break
    return lines


def parse_upload(filename: str, data: bytes) -> List[Dict[str, Any]]:
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return parse_xlsx(data)
    if name.endswith((".csv", ".txt", ".tsv")):
        return parse_csv(data)
    raise ValueError("รองรับเฉพาะไฟล์ .xlsx .xlsm .csv .txt")


# ---------------------------------------------------------------- จับคู่สินค้า
def _match_tokens(text: str) -> List[str]:
    out: List[str] = []
    for token in epicor.tokens(text):
        if len(token) < 2 or token in STOPWORDS:
            continue
        out.append(token)
    return out[:12]


def _similarity(query: str, doc: Dict[str, Any], toks: List[str]) -> float:
    """0–1 · ยิ่งมากยิ่งน่าจะใช่ — อ่านง่ายกว่าแต้มดิบของหน้าค้นหา

    ผสมสามอย่าง: สัดส่วนคำที่ตรง, ความเหมือนของทั้งข้อความ, และโบนัสเมื่อรหัสตรง
    """
    desc = epicor.norm(doc.get("description"))
    part_c = epicor.compact(doc.get("partNum"))
    query_n = epicor.norm(query)

    hit = 0.0
    for token in toks:
        if re.search(r"\b" + re.escape(token), desc):
            hit += 1.0
        elif token in desc:
            hit += 0.7
        elif token in part_c:
            hit += 0.5
    coverage = hit / len(toks) if toks else 0.0

    ratio = SequenceMatcher(None, query_n, desc).ratio() if desc else 0.0
    score = 0.68 * coverage + 0.32 * ratio

    query_c = epicor.compact(query)
    if query_c and part_c and (part_c == query_c or query_c in part_c):
        score = max(score, 0.95)
    # ของที่ซื้อบ่อยได้เปรียบเล็กน้อยเมื่อคะแนนสูสี — แต่ไม่มากพอจะกลบความไม่ตรง
    times = int((doc.get("stats") or {}).get("timesOrdered") or 0)
    score += min(times, 20) * 0.002
    return round(min(score, 1.0), 4)


def confidence_of(score: float) -> str:
    if score >= CONFIDENT:
        return "high"
    if score >= MAYBE:
        return "medium"
    return "low"


async def find_candidates(text: str, limit: int = TOP_CANDIDATES) -> List[Dict[str, Any]]:
    """หาสินค้าที่ "น่าจะใช่" สำหรับข้อความหนึ่งบรรทัดของ BOM

    ใช้ OR ระหว่างคำ ไม่ใช่ AND — คำอธิบายใน BOM มักมีคำที่ไม่มีในระบบปนอยู่
    ถ้าบังคับให้ตรงทุกคำจะไม่เจออะไรเลย
    """
    toks = _match_tokens(text)
    if not toks:
        return []

    db = get_database()
    query: Dict[str, Any] = {"$or": [epicor.token_filter(t) for t in toks]}
    docs = await db[schema.EP_ITEMS].find(query, epicor.ITEM_FIELDS).to_list(MAX_CANDIDATES)
    if not docs:
        return []

    scored: List[Tuple[float, Dict[str, Any]]] = [
        (_similarity(text, d, toks), d) for d in docs
    ]
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("partNum", "")))
    top = scored[:limit]

    prices = await epicor.prices_for([d.get("partNum", "") for _, d in top])
    out: List[Dict[str, Any]] = []
    for score, doc in top:
        view = epicor.item_view(doc, prices.get(doc.get("partNum", "")))
        view["match_score"] = score
        view["confidence"] = confidence_of(score)
        out.append(view)
    return out


TIE_GAP = 0.05          # คะแนนต่างกันไม่เกินนี้ = ถือว่าเสมอกัน
SPREAD_ALERT = 3.0      # ราคาต่างกันเกินนี้เท่า = ต้องเตือนให้คนเลือกเอง


def _ambiguity(cands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """เตือนเมื่อมีหลายรหัสที่ "ตรงพอ ๆ กัน" แต่ราคาห่างกันมาก

    ของจริงมีรหัสต่างกันหลายตัวที่คำอธิบายเหมือนกันเป๊ะ แต่ราคาคนละเรื่อง
    หยิบตัวแรกมาเงียบ ๆ แล้วบอกว่านี่คืองบ — ผิดได้เป็นสิบเท่าโดยไม่มีใครรู้
    """
    if not cands:
        return {"ambiguous": False, "alt_count": 0}
    best = cands[0]["match_score"]
    near = [c for c in cands
            if best - c["match_score"] <= TIE_GAP and c.get("last_price") is not None]
    if len(near) < 2:
        return {"ambiguous": False, "alt_count": max(len(near) - 1, 0)}

    prices = [float(c["last_price"]) for c in near if float(c["last_price"]) > 0]
    if len(prices) < 2:
        return {"ambiguous": False, "alt_count": len(near) - 1}
    low, high = min(prices), max(prices)
    ratio = round(high / low, 1) if low > 0 else None
    return {
        "ambiguous": bool(ratio and ratio >= SPREAD_ALERT),
        "alt_count": len(near) - 1,
        "alt_price_min": round(low, 2),
        "alt_price_max": round(high, 2),
        "alt_price_ratio": ratio,
    }


async def _match_one(line: Dict[str, Any]) -> Dict[str, Any]:
    """จับคู่บรรทัดเดียว — รหัสที่ระบุมาใน BOM ชนะเสมอ"""
    hint = _clean(line.get("part_hint"))
    if hint:
        doc = await epicor.get_item(hint)
        if doc:
            return {"part_num": doc["part_num"], "score": 1.0, "source": "part_hint",
                    "ambiguous": False, "alt_count": 0}

    cands = await find_candidates(line.get("name", ""), limit=6)
    found = _ambiguity(cands)
    if cands and cands[0]["match_score"] >= MATCH_FLOOR:
        found.update(part_num=cands[0]["part_num"], score=cands[0]["match_score"],
                     source="auto")
    else:
        found.update(part_num="", score=cands[0]["match_score"] if cands else 0.0,
                     source="none")
    return found


async def match_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """จับคู่ทุกบรรทัด แล้วคืนบรรทัดที่พร้อมเก็บลงฐานข้อมูล"""
    out: List[Dict[str, Any]] = []
    for index, line in enumerate(lines):
        found = await _match_one(line)
        out.append({
            "line_no": index + 1,
            "name": _clean(line.get("name"))[:300],
            "qty": float(line.get("qty") or 1),
            "uom": _clean(line.get("uom"))[:20],
            "part_hint": _clean(line.get("part_hint"))[:60],
            "remark": _clean(line.get("remark"))[:300],
            "part_num": found["part_num"],
            "match_score": found["score"],
            "match_source": found["source"],
            "ambiguous": found.get("ambiguous", False),
            "alt_count": found.get("alt_count", 0),
            "alt_price_min": found.get("alt_price_min"),
            "alt_price_max": found.get("alt_price_max"),
            "alt_price_ratio": found.get("alt_price_ratio"),
            "manual_price": None,
        })
    return out


# ---------------------------------------------------------------- คิดเงิน
def _age_days(when: Any) -> Optional[int]:
    if not when:
        return None
    try:
        moment = when if hasattr(when, "year") else None
        if moment is None:
            return None
        now = utcnow()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=now.tzinfo)
        return max((now - moment).days, 0)
    except (TypeError, ValueError):
        return None


async def _line_views(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    parts = [l.get("part_num") for l in lines if l.get("part_num")]
    db = get_database()
    docs = await db[schema.EP_ITEMS].find(
        {"partNum": {"$in": parts}}, epicor.ITEM_FIELDS
    ).to_list(len(parts) or 1) if parts else []
    by_part = {d.get("partNum"): d for d in docs}
    prices = await epicor.prices_for(parts) if parts else {}

    views: List[Dict[str, Any]] = []
    for line in lines:
        part = line.get("part_num") or ""
        item = by_part.get(part)
        view = epicor.item_view(item, prices.get(part)) if item else None
        manual = line.get("manual_price")

        if manual is not None:
            unit_price = float(manual)
            price_source = "manual"
            price_date = None
            price_vendor = ""
        elif view and view.get("last_price") is not None:
            unit_price = float(view["last_price"])
            price_source = "last_price"
            price_date = view.get("last_price_date")
            price_vendor = view.get("last_price_vendor") or ""
        else:
            unit_price = None
            price_source = "none"
            price_date = None
            price_vendor = ""

        qty = float(line.get("qty") or 0)
        age = _age_days(price_date)
        views.append({
            "line_no": line.get("line_no"),
            "name": line.get("name", ""),
            "qty": qty,
            "uom": line.get("uom") or (view or {}).get("uom") or "",
            "remark": line.get("remark", ""),
            "part_hint": line.get("part_hint", ""),
            "part_num": part,
            "matched": bool(part),
            "match_score": line.get("match_score") or 0.0,
            "match_source": line.get("match_source") or "none",
            "confidence": confidence_of(float(line.get("match_score") or 0.0)),
            "ambiguous": bool(line.get("ambiguous")) and line.get("match_source") == "auto",
            "alt_count": line.get("alt_count") or 0,
            "alt_price_min": line.get("alt_price_min"),
            "alt_price_max": line.get("alt_price_max"),
            "alt_price_ratio": line.get("alt_price_ratio"),
            "item_description": (view or {}).get("description", ""),
            "item_uom": (view or {}).get("uom", ""),
            "vendor_count": (view or {}).get("vendor_count", 0),
            "unit_price": unit_price,
            "price_source": price_source,
            "price_date": price_date,
            "price_vendor": price_vendor,
            "price_age_days": age,
            "price_stale": bool(age is not None and age > STALE_DAYS),
            "lowest_price": (view or {}).get("lowest_price"),
            "highest_price": (view or {}).get("highest_price"),
            "manual_price": manual,
            "amount": round(unit_price * qty, 2) if unit_price is not None else None,
            "priced": unit_price is not None,
            # ออกใบขอราคาไปแล้วหรือยัง — ไม่งั้นกดซ้ำแล้วได้ใบซ้ำโดยไม่รู้ตัว
            # หนึ่งบรรทัดอาจอยู่ในใบของผู้ขายหลายเจ้า (ตอนรวมใบตามผู้ขาย) จึงเก็บเป็นรายการ
            "rfqs": [
                {"rfq_id": str(r.get("rfq_id")), "rfq_no": r.get("rfq_no", ""),
                 "vendor_key": r.get("vendor_key", "")}
                for r in (line.get("rfqs") or [])
            ] or ([{"rfq_id": str(line["rfq_id"]), "rfq_no": line.get("rfq_no", ""),
                    "vendor_key": ""}] if line.get("rfq_id") else []),
            "rfq_id": str(line["rfq_id"]) if line.get("rfq_id") else "",
            "rfq_no": line.get("rfq_no", ""),
        })
    return views


def totals_of(views: List[Dict[str, Any]], contingency: float, vat: float) -> Dict[str, Any]:
    """ยอดรวม + ตัวเลขที่บอกว่ายอดนี้เชื่อได้แค่ไหน

    ตั้งใจส่ง unpriced_lines / coverage_percent ไปด้วยเสมอ เพราะยอดรวมที่เงียบ ๆ
    ข้ามรายการที่ยังไม่มีราคา จะถูกอ่านว่า "งบทั้งโครงการ" ทั้งที่ไม่ใช่
    """
    priced = [v for v in views if v["priced"]]
    subtotal = round(sum(v["amount"] or 0 for v in priced), 2)
    contingency_amount = round(subtotal * contingency / 100.0, 2)
    before_vat = round(subtotal + contingency_amount, 2)
    vat_amount = round(before_vat * vat / 100.0, 2)
    stale = [v for v in priced if v["price_stale"]]
    low = [v for v in views if v["matched"] and v["confidence"] == "low"]

    return {
        "line_count": len(views),
        "priced_lines": len(priced),
        "unpriced_lines": len(views) - len(priced),
        "unmatched_lines": len([v for v in views if not v["matched"] and v["manual_price"] is None]),
        "low_confidence_lines": len(low),
        "ambiguous_lines": len([v for v in views if v["ambiguous"]]),
        "stale_price_lines": len(stale),
        "coverage_percent": round(len(priced) * 100.0 / len(views), 1) if views else 0.0,
        "subtotal": subtotal,
        "contingency_percent": contingency,
        "contingency_amount": contingency_amount,
        "before_vat": before_vat,
        "vat_percent": vat,
        "vat_amount": vat_amount,
        "total": round(before_vat + vat_amount, 2),
    }


async def build_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    lines = doc.get("lines") or []
    views = await _line_views(lines)
    await attach_progress(views)
    return {
        "id": str(doc.get("_id")),
        "bom_no": doc.get("bom_no", ""),
        "title": doc.get("title", ""),
        "note": doc.get("note", ""),
        "status": doc.get("status", "draft"),
        "currency": doc.get("currency", "THB"),
        "contingency_percent": doc.get("contingency_percent", 10),
        "vat_percent": doc.get("vat_percent", 7),
        "created_at": doc.get("created_at"),
        "created_by": doc.get("created_by", ""),
        "updated_at": doc.get("updated_at"),
        "rfq_id": doc.get("rfq_id"),
        "rfq_no": doc.get("rfq_no", ""),
        "lines": views,
        "totals": totals_of(views, float(doc.get("contingency_percent") or 0),
                            float(doc.get("vat_percent") or 0)),
        "progress": progress_summary(views),
    }


def summary_view(doc: Dict[str, Any]) -> Dict[str, Any]:
    """แถวในหน้ารายการ — ใช้ค่าที่เก็บไว้ตอนบันทึก ไม่ต้องคิดใหม่ทุกครั้ง"""
    cached = doc.get("totals") or {}
    return {
        "id": str(doc.get("_id")),
        "bom_no": doc.get("bom_no", ""),
        "title": doc.get("title", ""),
        "status": doc.get("status", "draft"),
        "currency": doc.get("currency", "THB"),
        "line_count": len(doc.get("lines") or []),
        "priced_lines": cached.get("priced_lines", 0),
        "coverage_percent": cached.get("coverage_percent", 0.0),
        "total": cached.get("total"),
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
        "created_by": doc.get("created_by", ""),
        "rfq_no": doc.get("rfq_no", ""),
        "progress": doc.get("progress") or {},
    }


# ---------------------------------------------------------------- ออก RFQ แยกรายตัว
MAX_SUGGEST = 3         # ติ๊กไว้ให้กี่ราย — ที่เหลือให้คนเลือกเอง


async def invited_vendors(line: Dict[str, Any]) -> Dict[str, List[str]]:
    """ผู้ขายที่ "เคยถูกเชิญให้เสนอราคาของบรรทัดนี้แล้ว" → เลขที่ใบที่เชิญ

    ถามจาก rfq_invites เสมอ ไม่ใช่จาก vendor_key ที่จดไว้ที่บรรทัด เพราะใบที่ออก
    แบบรวมผู้ขายหลายเจ้าไว้ในใบเดียวจะไม่มี vendor_key ติดมากับบรรทัด
    ถ้าเชื่อค่าที่จดไว้อย่างเดียว จะสรุปว่า "ยังไม่เคยเชิญ" ทั้งที่เชิญไปแล้ว
    แล้วออกใบซ้ำไปหาเจ้าเดิม
    """
    from bson import ObjectId

    rows = line.get("rfqs") or []
    ids: List[Any] = []
    no_by_id: Dict[str, str] = {}
    for row in rows:
        try:
            oid = ObjectId(str(row.get("rfq_id")))
        except Exception:       # noqa: BLE001
            continue
        ids.append(oid)
        no_by_id[str(oid)] = row.get("rfq_no", "")

    out: Dict[str, List[str]] = {}
    if not ids:
        return out

    db = get_database()
    invites = await db[schema.RFQ_INVITES].find(
        {"rfq_id": {"$in": ids}}, {"rfq_id": 1, "vendor_key": 1}
    ).to_list(None)
    for inv in invites:
        out.setdefault(inv["vendor_key"], []).append(no_by_id.get(str(inv["rfq_id"]), ""))
    return out


def mark_invited(vendors: List[Dict[str, Any]], invited: Dict[str, List[str]]) -> None:
    """ติดธงว่าเจ้าไหนเชิญไปแล้ว — ให้คนเลือกเห็นก่อนกด ไม่ใช่ไปรู้ตอนออกใบซ้ำ"""
    for vendor in vendors:
        nos = invited.get(vendor.get("vendor_key", ""))
        vendor["invited"] = bool(nos)
        vendor["invited_rfqs"] = [n for n in (nos or []) if n]


async def rfq_plan(doc: Dict[str, Any], line_no: Optional[int] = None) -> Dict[str, Any]:
    """เตรียมข้อมูล "จะออกใบขอราคาแยกใบต่อรายการ" ให้หน้าเว็บใช้ในครั้งเดียว

    แต่ละรายการพกรายชื่อผู้ขายที่ **เคยขายรหัสนี้จริง** มาด้วย พร้อมราคาล่าสุด
    ของผู้ขายรายนั้นและคะแนนความตรงเวลา — เพื่อให้เลือกได้จากข้อมูล
    ไม่ใช่เลือกจากความคุ้นชื่อ
    """
    lines = doc.get("lines") or []
    if line_no is not None:
        # หน้าวัสดุรายตัวขอแค่บรรทัดเดียว — ไม่ต้องไปยิง Epicor ให้ครบทุกบรรทัดของโครงการ
        lines = [l for l in lines if l.get("line_no") == line_no]
    views = await _line_views(lines)

    items: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for view in views:
        if not view["matched"]:
            skipped.append({
                "line_no": view["line_no"], "name": view["name"],
                "reason": "ยังไม่ได้จับคู่กับสินค้าในระบบ",
            })
            continue

        item = await epicor.get_item(view["part_num"])
        vendors = (item or {}).get("vendors") or []
        # ราคาอย่างเดียวไม่พอ — เจ้าถูกสุดที่ส่งช้าประจำก็มี ต้องเห็นสองอย่างพร้อมกัน
        await delivery.attach_scores(vendors)
        per_item = await delivery.item_vendor_delivery(view["part_num"])
        for vendor in vendors:
            vendor["delivery_this_item"] = per_item.get(str(vendor.get("vendor_id") or ""))
        invited = await invited_vendors(view)
        mark_invited(vendors, invited)
        # ติ๊กไว้ให้เฉพาะรายที่มีราคาจริงและยังไม่เคยเชิญ เรียงจากถูกสุด
        # ราคาไม่มีก็เดาไม่ได้ว่าใครคุ้ม ส่วนเจ้าที่เชิญไปแล้วไม่ควรติ๊กซ้ำให้เอง
        priced = [v for v in vendors
                  if v.get("last_unit_cost") is not None and not v.get("invited")]
        suggested = {v["vendor_key"] for v in priced[:MAX_SUGGEST]}
        for vendor in vendors:
            vendor["suggested"] = vendor["vendor_key"] in suggested

        items.append({
            "line_no": view["line_no"],
            "name": view["name"],
            "part_num": view["part_num"],
            "item_description": view["item_description"],
            "qty": view["qty"],
            "uom": view["uom"] or view["item_uom"],
            "unit_price": view["unit_price"],
            "price_date": view["price_date"],
            "confidence": view["confidence"],
            "ambiguous": view["ambiguous"],
            "rfq_no": view["rfq_no"],
            "vendor_count": len(vendors),
            "vendors": vendors,
        })

    return {
        "bom_no": doc.get("bom_no", ""),
        "title": doc.get("title", ""),
        "currency": doc.get("currency", "THB"),
        "items": items,
        "skipped": skipped,
        "suggest_limit": MAX_SUGGEST,
    }


async def vendors_for_similar(text: str, limit: int = 12) -> Dict[str, Any]:
    """หาผู้ขายจาก "อุปกรณ์ที่ใกล้เคียง" ไม่ใช่จากชื่อผู้ขาย

    ใช้ตอนอยากเชิญเจ้าอื่นเพิ่ม แต่ไม่รู้ว่าใครขายของแบบนี้ —
    ค้นสินค้าที่คล้ายกันก่อน แล้วดูว่าใครเคยขายของพวกนั้นให้เรา
    บอกด้วยเสมอว่า "มาจากสินค้าตัวไหน" ไม่งั้นรายชื่อจะดูเหมือนคำแนะนำลอย ๆ
    ที่ตรวจย้อนกลับไม่ได้
    """
    candidates = await find_candidates(text, limit=6)
    if not candidates:
        return {"query": text, "items": [], "via_items": []}

    by_vendor: Dict[str, Dict[str, Any]] = {}
    for cand in candidates:
        item = await epicor.get_item(cand["part_num"])
        for vendor in (item or {}).get("vendors") or []:
            row = by_vendor.setdefault(vendor["vendor_key"], {
                "vendor_key": vendor["vendor_key"],
                "vendor_id": vendor["vendor_id"],
                "name": vendor["name"],
                "po_count": 0,
                "match_score": 0.0,
                "via_items": [],
            })
            row["match_score"] = max(row["match_score"], cand["match_score"])
            row["po_count"] += int(vendor.get("times") or 0)
            row["via_items"].append({
                "part_num": cand["part_num"],
                "description": cand["description"],
                "last_unit_cost": vendor.get("last_unit_cost"),
                "match_score": cand["match_score"],
            })

    rows = list(by_vendor.values())
    for row in rows:
        row["via_items"].sort(key=lambda i: -i["match_score"])
        row["via_items"] = row["via_items"][:3]
    rows.sort(key=lambda r: (-r["match_score"], -r["po_count"], r["name"]))
    rows = rows[:limit]
    await delivery.attach_scores(rows)

    return {
        "query": text,
        "items": rows,
        "via_items": [{"part_num": c["part_num"], "description": c["description"],
                       "match_score": c["match_score"]} for c in candidates],
    }


# ---------------------------------------------------------------- สถานะงาน
# ขั้นตอนของ "หนึ่งรายการ" ตั้งแต่ตั้งงบจนอนุมัติราคา
# ทุกขั้นอ่านจากข้อมูลจริง (สถานะใบขอราคา / ใบเสนอราคาที่เข้ามา / ผลประกาศผู้ชนะ)
# ไม่ใช่ธงที่คนกดเอง — ธงที่กดเองจะค้างอยู่ที่ค่าเก่าทันทีที่มีคนลืมกด
STAGES = [
    ("no_match", "ยังไม่จับคู่"),
    ("estimated", "ตีราคาแล้ว"),
    ("rfq_draft", "ออกใบขอราคาแล้ว"),
    ("rfq_sent", "ส่งให้ผู้ขายแล้ว"),
    ("quoted", "ได้รับราคาแล้ว"),
    ("awarded", "อนุมัติราคาแล้ว"),
]
STAGE_LABEL = dict(STAGES)
STAGE_ORDER = {key: i for i, (key, _) in enumerate(STAGES)}


async def _rfq_progress(rfq_ids: List[Any]) -> Dict[str, Dict[str, Any]]:
    """สรุปสถานะของใบขอราคาที่ออกไปแล้ว — คีย์เป็น str(rfq_id)"""
    if not rfq_ids:
        return {}
    db = get_database()
    rfqs = await db[schema.RFQS].find(
        {"_id": {"$in": rfq_ids}},
        {"rfq_no": 1, "status": 1, "sent_at": 1, "awards": 1, "awarded_at": 1, "currency": 1},
    ).to_list(len(rfq_ids))

    counts: Dict[str, int] = {}
    for row in await db[schema.RFQ_QUOTES].find(
        {"rfq_id": {"$in": rfq_ids}}, {"rfq_id": 1, "submitted_at": 1}
    ).to_list(None):
        # ใบที่มีแต่ไฟล์แนบยังไม่นับว่า "เสนอราคาแล้ว" เพราะยังไม่มีตัวเลขให้เทียบ
        if row.get("submitted_at"):
            counts[str(row["rfq_id"])] = counts.get(str(row["rfq_id"]), 0) + 1

    out: Dict[str, Dict[str, Any]] = {}
    for rfq in rfqs:
        key = str(rfq["_id"])
        quote_count = counts.get(key, 0)
        awards = rfq.get("awards") or []
        if awards:
            stage = "awarded"
        elif quote_count:
            stage = "quoted"
        elif rfq.get("sent_at") or rfq.get("status") in ("sent", "closed"):
            stage = "rfq_sent"
        else:
            stage = "rfq_draft"
        out[key] = {
            "stage": stage,
            "rfq_no": rfq.get("rfq_no", ""),
            "rfq_status": rfq.get("status", ""),
            "sent_at": rfq.get("sent_at"),
            "quote_count": quote_count,
            "awards": awards,
            "awarded_at": rfq.get("awarded_at"),
        }
    return out


def _award_for(progress: Dict[str, Any], part_num: str) -> Optional[Dict[str, Any]]:
    for row in progress.get("awards") or []:
        if str(row.get("part_num")) == part_num:
            return row
    return None


async def attach_progress(views: List[Dict[str, Any]]) -> None:
    """เติมสถานะให้ทุกบรรทัด (แก้ไขในที่)

    บรรทัดหนึ่งอาจอยู่ในใบของผู้ขายหลายเจ้า จึงถือ **ขั้นที่ไกลที่สุด** เป็นสถานะของบรรทัด —
    ถ้ามีเจ้าหนึ่งอนุมัติราคาแล้ว ของชิ้นนั้นก็จบแล้วจริง ๆ ต่อให้ใบของอีกเจ้ายังรอตอบอยู่
    """
    from bson import ObjectId

    ids = []
    for view in views:
        for row in view.get("rfqs") or []:
            try:
                ids.append(ObjectId(row["rfq_id"]))
            except Exception:       # noqa: BLE001 — id เพี้ยนไม่ควรทำให้ทั้งหน้าพัง
                continue
    progress = await _rfq_progress(ids)

    for view in views:
        infos = [progress[r["rfq_id"]] for r in (view.get("rfqs") or [])
                 if r["rfq_id"] in progress]
        view["rfq_count"] = len(infos)
        if not infos:
            stage = "estimated" if view["matched"] or view["priced"] else "no_match"
            view["stage"] = stage
            view["stage_label"] = STAGE_LABEL[stage]
            view["quote_count"] = 0
            view["award"] = None
            continue

        best = max(infos, key=lambda i: STAGE_ORDER[i["stage"]])
        award = next(
            (a for i in infos for a in [_award_for(i, view["part_num"])] if a), None
        )
        view["stage"] = best["stage"]
        view["stage_label"] = STAGE_LABEL[best["stage"]]
        view["rfq_status"] = best["rfq_status"]
        view["quote_count"] = sum(i["quote_count"] for i in infos)
        view["award"] = None
        if award:
            approved = award.get("unit_price")
            estimate = view.get("unit_price")
            view["award"] = {
                "vendor_name": award.get("vendor_name", ""),
                "vendor_key": award.get("vendor_key", ""),
                "unit_price": approved,
                "amount": award.get("amount"),
                "awarded_at": next((i.get("awarded_at") for i in infos if i.get("awarded_at")),
                                   None),
                # ต่างจากงบที่ตั้งไว้กี่ % — บวกคือแพงกว่างบ
                "vs_estimate_pct": (
                    round((approved - estimate) / estimate * 100, 1)
                    if approved is not None and estimate else None
                ),
            }


def progress_summary(views: List[Dict[str, Any]]) -> Dict[str, Any]:
    """ภาพรวมว่าโครงการนี้เดินไปถึงไหนแล้ว + งบที่ตั้งไว้เทียบราคาที่อนุมัติจริง"""
    by_stage = {key: 0 for key, _ in STAGES}
    for view in views:
        by_stage[view.get("stage", "no_match")] = by_stage.get(view.get("stage", "no_match"), 0) + 1

    awarded = [v for v in views if v.get("award")]
    approved_amount = round(sum(v["award"].get("amount") or 0 for v in awarded), 2)
    estimate_of_awarded = round(sum(v.get("amount") or 0 for v in awarded), 2)

    done = sum(by_stage[k] for k in ("rfq_draft", "rfq_sent", "quoted", "awarded"))
    return {
        "stages": [
            {"key": key, "label": label, "count": by_stage[key]} for key, label in STAGES
        ],
        "asked_lines": done,                       # ออกใบขอราคาไปแล้วกี่รายการ
        "awarded_lines": by_stage["awarded"],
        "waiting_lines": by_stage["rfq_sent"],
        "approved_amount": approved_amount,
        "estimate_of_awarded": estimate_of_awarded,
        "approved_vs_estimate_pct": (
            round((approved_amount - estimate_of_awarded) / estimate_of_awarded * 100, 1)
            if estimate_of_awarded else None
        ),
    }


# ---------------------------------------------------------------- เทียบราคารายสินค้า
async def comparison(doc: Dict[str, Any]) -> Dict[str, Any]:
    """เทียบราคาทั้งโครงการ โดยมองเป็น "รายสินค้า" ไม่ใช่รายผู้ขาย

    ใบขอราคาออกเป็นใบต่อผู้ขาย (เขาจะได้ตอบครั้งเดียวจบ) แต่เวลาตัดสินใจ
    คำถามคือ "ของชิ้นนี้ ใครให้ราคาดีที่สุด" ไม่ใช่ "ใบนี้ใครถูกสุด" —
    จึงต้องรวมราคาจากทุกใบของโครงการกลับมาเรียงเป็นแถวละสินค้า

    ทุกช่องที่ว่างมีความหมายต่างกัน และต้องแยกให้ออก:
      ยังไม่ได้เชิญ / เชิญแล้วยังไม่ตอบ / ตอบแล้วแต่แจ้งว่าไม่เสนอรายการนี้
    ถ้าแสดงเป็นขีดเหมือนกันหมด คนอ่านจะสรุปผิดว่า "เจ้านี้ไม่มีของ"
    """
    from bson import ObjectId

    db = get_database()
    views = await _line_views(doc.get("lines") or [])
    await attach_progress(views)

    rfq_ids: List[Any] = []
    for view in views:
        for row in view.get("rfqs") or []:
            try:
                rfq_ids.append(ObjectId(row["rfq_id"]))
            except Exception:       # noqa: BLE001
                continue
    if not rfq_ids:
        return {"vendors": [], "rows": [], "summary": {"quoted_vendors": 0, "quoted_lines": 0},
                "currency": doc.get("currency", "THB")}

    invites = await db[schema.RFQ_INVITES].find(
        {"rfq_id": {"$in": rfq_ids}},
        {"rfq_id": 1, "vendor_key": 1, "vendor_id": 1, "vendor_name": 1, "status": 1},
    ).to_list(None)
    quotes = await db[schema.RFQ_QUOTES].find({"rfq_id": {"$in": rfq_ids}}).to_list(None)

    # ผู้ขายรายหนึ่งอาจถูกเชิญในหลายใบของโครงการเดียวกัน — รวมเป็นคอลัมน์เดียว
    vendors: Dict[str, Dict[str, Any]] = {}
    for inv in invites:
        row = vendors.setdefault(inv["vendor_key"], {
            "vendor_key": inv["vendor_key"],
            "vendor_id": inv.get("vendor_id", ""),
            "vendor_name": inv.get("vendor_name", ""),
            "invited_rfqs": [],
            "quoted_lines": 0,
            "total": 0.0,
            "has_quote": False,
        })
        row["invited_rfqs"].append(str(inv["rfq_id"]))

    # ราคาที่เสนอมา: (ผู้ขาย, รหัสสินค้า) -> บรรทัดในใบเสนอราคา
    quoted: Dict[Any, Dict[str, Any]] = {}
    for quote in quotes:
        if not quote.get("submitted_at"):
            continue
        vendors.setdefault(quote["vendor_key"], {
            "vendor_key": quote["vendor_key"], "vendor_id": quote.get("vendor_id", ""),
            "vendor_name": quote.get("vendor_name", ""), "invited_rfqs": [],
            "quoted_lines": 0, "total": 0.0, "has_quote": False,
        })["has_quote"] = True
        for line in quote.get("lines", []):
            quoted[(quote["vendor_key"], str(line.get("part_num")))] = line

    rows: List[Dict[str, Any]] = []
    for view in views:
        if not view["matched"] or not view.get("rfqs"):
            continue
        part = view["part_num"]
        qty = float(view["qty"] or 0)
        mine = {r["vendor_key"] for r in (view.get("rfqs") or []) if r.get("vendor_key")}

        cells = []
        for key, vendor in vendors.items():
            invited = (not mine) or key in mine
            line = quoted.get((key, part))
            unit = None if not line or line.get("no_quote") else line.get("unit_price")
            cells.append({
                "vendor_key": key,
                "unit_price": unit,
                "amount": round(unit * qty, 2) if unit is not None else None,
                "lead_time_days": (line or {}).get("lead_time_days"),
                # แยกสามกรณีของช่องว่างให้ชัด
                "invited": invited,
                "answered": bool(line),
                "no_quote": bool(line and line.get("no_quote")),
                "is_lowest": False,
            })

        priced = [c for c in cells if c["amount"] is not None]
        if priced:
            lowest = min(priced, key=lambda c: c["amount"])
            lowest["is_lowest"] = True
        for cell in priced:
            vendors[cell["vendor_key"]]["quoted_lines"] += 1
            vendors[cell["vendor_key"]]["total"] += cell["amount"] or 0
        cells_by_key = {c["vendor_key"]: c for c in cells}

        best = min((c["unit_price"] for c in priced), default=None)
        estimate = view.get("unit_price")
        rows.append({
            "line_no": view["line_no"],
            "name": view["name"],
            "part_num": part,
            "item_description": view["item_description"],
            "qty": qty,
            "uom": view["uom"],
            "estimate_unit_price": estimate,
            "estimate_amount": view.get("amount"),
            "stage": view["stage"],
            "stage_label": view["stage_label"],
            "award": view.get("award"),
            "best_unit_price": best,
            # ถูกกว่างบที่ตั้งไว้กี่ % (ลบ = ถูกกว่า)
            "best_vs_estimate_pct": (
                round((best - estimate) / estimate * 100, 1)
                if best is not None and estimate else None
            ),
            "quoted_count": len(priced),
            "cells": cells,
            "_cells_by_key": cells_by_key,
        })

    for vendor in vendors.values():
        vendor["total"] = round(vendor["total"], 2)

    ordered = sorted(
        vendors.values(),
        key=lambda v: (not v["has_quote"], -v["quoted_lines"], v["vendor_name"]),
    )
    await delivery.attach_scores(ordered)

    # ช่องในแต่ละแถวต้องเรียงตรงกับลำดับคอลัมน์เป๊ะ ๆ
    # ถ้าเรียงคนละแบบ ราคาของเจ้าหนึ่งจะไปโผล่ใต้ชื่ออีกเจ้าหนึ่งแบบเงียบ ๆ
    # เป็นความผิดที่มองไม่เห็นจากหน้าจอเลย และทำให้เลือกผู้ชนะผิดตัว
    for row in rows:
        by_key = row.pop("_cells_by_key")
        row["cells"] = [by_key[v["vendor_key"]] for v in ordered]

    best_total = round(sum(r["best_unit_price"] * r["qty"] for r in rows
                           if r["best_unit_price"] is not None), 2)
    estimate_total = round(sum(r["estimate_amount"] or 0 for r in rows
                               if r["best_unit_price"] is not None), 2)
    return {
        "currency": doc.get("currency", "THB"),
        "vendors": ordered,
        "rows": rows,
        "summary": {
            "line_count": len(rows),
            "quoted_lines": len([r for r in rows if r["quoted_count"]]),
            "waiting_lines": len([r for r in rows if not r["quoted_count"]]),
            "quoted_vendors": len([v for v in ordered if v["has_quote"]]),
            "invited_vendors": len(ordered),
            # เลือกเจ้าที่ถูกที่สุดของแต่ละชิ้นแล้วจะจ่ายรวมเท่าไร
            "best_total": best_total,
            "estimate_total": estimate_total,
            "best_vs_estimate_pct": (
                round((best_total - estimate_total) / estimate_total * 100, 1)
                if estimate_total else None
            ),
        },
    }
