"""สร้างข้อมูลจำลอง epicor_procurement ใน MongoDB ของเครื่องทดสอบ

โครงสร้างทุกฟิลด์ยึดตาม docs/mongodb_schema.md และ scripts/04_etl_to_mongodb.py ของจริง
เพื่อให้โค้ดที่เขียนบนข้อมูลชุดนี้ ใช้กับฐานข้อมูลจริงได้ทันที
"""
import datetime as dt
import random
import os, pickle, sys
try:
    from pymongo import MongoClient
except Exception:
    MongoClient = None

random.seed(20260815)
COMPANY = "PSP"
NOW = dt.datetime(2026, 8, 15)
NO_PART = "(ไม่ระบุรหัส)"

DUMP_ONLY = os.environ.get("DUMP_ONLY") == "1"
SEED_FILE = os.environ.get("TEST_SEED", "/tmp/epicor_seed.pkl")
if not DUMP_ONLY:
    cli = MongoClient("mongodb://localhost:27017/")
    db = cli["epicor_procurement"]
    for c in ("vendors", "items", "item_last_price", "transactions", "etl_runs"):
        db[c].drop()

TH_PREFIX = ["บริษัท", "ห้างหุ้นส่วนจำกัด"]
TH_NAMES = [
    "วีเอสที อีซีเอส (ประเทศไทย)", "ซีวายจี ซันรี่ (ประเทศไทย)", "ฮิตาชิ เอนเนอร์ยี่ (ประเทศไทย)",
    "ซิมพลิซิตี้ เทคโนโลยี", "เบอร์ลี่ ยุคเกอร์", "ชไนเดอร์ (ไทยแลนด์)", "เอบีบี (ประเทศไทย)",
    "สยามคูโบต้า อีเลคทริค", "ไทยยาซากิ อิเล็คทริควายร์", "เพาเวอร์ไลน์ เอ็นจิเนียริ่ง",
    "อินเตอร์ลิ้งค์ คอมมิวนิเคชั่น", "ที.เอ็น.เมตัลเวิร์ค", "ยูนิเวอร์แซล ยูทีลิตี้ส์",
    "เอส.พี.เอส. อินเตอร์แนชั่นแนล", "ไทยเมอิระ", "แสงชัย มิเตอร์", "กันกุลเอ็นจิเนียริ่ง",
    "ทีพีไอ โพลีน", "เจริญชัยหม้อแปลงไฟฟ้า", "ถิรไทย", "เอ็มเอ็มพี คอร์ปอเรชั่น",
    "ไพโอเนียร์ มอเตอร์", "บางกอกเคเบิ้ล", "ฟูจิ อิเล็คทริค (ประเทศไทย)", "โอมรอน อีเลคทรอนิคส์",
]
EN_NAMES = [
    "Belden Singapore Pte Ltd.", "Siemens Ltd.", "Schneider Electric Asia", "Cisco Systems Thailand",
    "Dell Technologies Thailand", "Hewlett Packard Enterprise", "Phoenix Contact Thailand",
    "Rittal Ltd.", "Weidmuller Thailand", "Moxa Asia Pacific", "Advantech Thailand",
    "SEL Schweitzer Engineering", "GE Grid Solutions", "Eaton Electric Thailand",
    "Legrand Thailand", "Delta Electronics Thailand",
]
CATS = [
    ("1001", "อุปกรณ์ไฟฟ้ากำลัง"), ("1002", "อุปกรณ์สื่อสาร"), ("1003", "ตู้และโครงสร้าง"),
    ("1004", "สายไฟและอุปกรณ์ต่อ"), ("1005", "เครื่องมือวัด"), ("2001", "งานบริการ/ติดตั้ง"),
]
PRODUCTS = [
    ("ETHERNET SWITCH", "GRS1142-6T6ZEHH12V9HHSE3AMRXX", "1002", "EA"),
    ("DISTANCE PROTECTION RELAY", "REL670*2.2-A42X00-P23P30", "1001", "EA"),
    ("FRTU-RCS CYG", "PRS-3351 FIXPLATE TYPE. B", "1001", "set"),
    ("INSERTION BRIDGE", "TKO 6/2 (476282)", "1004", "each"),
    ("CURRENT TRANSFORMER", "CT 400/5A CLASS 0.5", "1005", "EA"),
    ("VOLTAGE TRANSFORMER", "VT 22kV/110V", "1005", "EA"),
    ("MEDIA CONVERTER", "IMC-101G-M-SC", "1002", "EA"),
    ("INDUSTRIAL ROUTER", "EDR-810-2GSFP", "1002", "EA"),
    ("POWER SUPPLY", "DRP-24V240W1AZ", "1001", "EA"),
    ("SURGE PROTECTION DEVICE", "VAL-MS 320/3+0", "1001", "EA"),
    ("TERMINAL BLOCK", "UT 2,5-MTD-DIO", "1004", "EA"),
    ("CONTROL CABLE", "FROH2R 4x2.5 SQ.MM", "1004", "M"),
    ("FIBER OPTIC CABLE", "SM 24C ADSS 100M SPAN", "1004", "M"),
    ("OUTDOOR CABINET", "IP55 1200x800x400 SS304", "1003", "EA"),
    ("DIN RAIL", "NS 35/7,5 PERF 2000MM", "1003", "EA"),
    ("SMART METER", "ION7650 CT/VT", "1005", "EA"),
    ("BATTERY CHARGER", "48VDC 30A RECTIFIER", "1001", "EA"),
    ("VACUUM CIRCUIT BREAKER", "VD4 24kV 1250A 25kA", "1001", "EA"),
    ("DISCONNECTING SWITCH", "GW 24kV 630A OUTDOOR", "1001", "EA"),
    ("RTU CONTROLLER", "SICAM A8000 CP-8050", "1001", "EA"),
    ("GPS TIME SERVER", "TSU-NTP-01", "1005", "EA"),
    ("SERVER RACK", "42U 800x1000 GLASS DOOR", "1003", "EA"),
    ("UPS SYSTEM", "10kVA ONLINE 3:1", "1001", "EA"),
    ("SCADA SOFTWARE LICENSE", "500 TAG PERPETUAL", "1002", "LIC"),
    ("NETWORK FIREWALL", "FG-100F BUNDLE 1Y", "1002", "EA"),
    ("PATCH PANEL", "24 PORT CAT6A UTP", "1004", "EA"),
    ("INSTALLATION SERVICE", "COMMISSIONING ON SITE", "2001", "JOB"),
    ("PREVENTIVE MAINTENANCE", "ANNUAL CONTRACT", "2001", "JOB"),
    ("CABLE GLAND", "M25 BRASS NICKEL PLATED", "1004", "EA"),
    ("EARTHING ROD", "COPPER BONDED 5/8x3M", "1004", "EA"),
]

# ------------------------------------------------------------------ vendors
vendor_rows = []
names = [f"{random.choice(TH_PREFIX)} {n} จำกัด" for n in TH_NAMES] + EN_NAMES
for i, name in enumerate(names, start=1):
    vid = "2{}{:06d}".format(random.choice([1, 2]), 10000 + i)
    vendor_rows.append({"vendorNum": i, "vendorId": vid, "name": name})

VN = {v["vendorNum"]: v for v in vendor_rows}


def rdate(y0=2021, y1=2026):
    start = dt.datetime(y0, 1, 1)
    end = dt.datetime(y1, 6, 30)
    return start + dt.timedelta(days=random.randint(0, (end - start).days))


# ------------------------------------------------------------------ items + PO lines
items, last_price, transactions = [], [], []
po_num = 1000
pack = 5000
inv = 70000

item_defs = []
for idx in range(240):
    base, spec, cat, uom = PRODUCTS[idx % len(PRODUCTS)]
    part = "{:02d}-{:03d}-{:02d}-{:02d}-{:03d}".format(
        1 if cat != "2001" else 3, (idx % 60) + 1, (idx % 19) + 1, (idx % 7) + 1, (idx % 97) + 1)
    if any(d["partNum"] == part for d in item_defs):
        part = part[:-3] + "{:03d}".format(idx + 200)
    item_defs.append({
        "partNum": part,
        "description": "{} ({})".format(base, spec),
        "classId": cat, "uom": uom,
    })

for d in item_defs:
    part, cat = d["partNum"], d["classId"]
    n_vendors = random.choices([1, 1, 1, 2, 2, 3, 4, 5], k=1)[0]
    vendors = random.sample(vendor_rows, n_vendors)
    base_cost = round(random.choice([120, 480, 1250, 6400, 18500, 70000, 185000]) *
                      random.uniform(0.8, 1.25), 2)

    po_rows = []
    for v in vendors:
        for _ in range(random.randint(1, 6)):
            po_num += 1
            date = rdate()
            unit = round(base_cost * random.uniform(0.7, 1.9), 2)
            qty = float(random.choice([1, 2, 4, 5, 10, 12, 20, 50, 100]))
            po_rows.append({"v": v, "date": date, "unit": unit, "qty": qty,
                            "poNum": po_num, "poLine": random.randint(1, 4)})

    # ---- transactions (PO / รับของ / ใบแจ้งหนี้)
    for r in po_rows:
        transactions.append({
            "_id": "{}|PO|{}|{}".format(COMPANY, r["poNum"], r["poLine"]),
            "docType": "PO_LINE", "company": COMPANY, "date": r["date"],
            "vendor": {"num": r["v"]["vendorNum"], "id": r["v"]["vendorId"], "name": r["v"]["name"]},
            "part": {"num": part, "description": d["description"], "uom": d["uom"]},
            "qty": r["qty"], "unitCost": r["unit"], "amount": round(r["qty"] * r["unit"], 2),
            "currency": "THB", "ref": {"poNum": r["poNum"], "poLine": r["poLine"]},
            "meta": {"classId": cat, "buyerId": "PUR_10{}".format(random.randint(1, 4)),
                     "dueDate": r["date"] + dt.timedelta(days=45), "openLine": random.random() < 0.1},
        })
        if random.random() < 0.85:
            pack += 1
            transactions.append({
                "_id": "{}|RCV|{}|1".format(COMPANY, pack),
                "docType": "RECEIPT_LINE", "company": COMPANY,
                "date": r["date"] + dt.timedelta(days=random.randint(7, 60)),
                "vendor": {"num": r["v"]["vendorNum"], "id": r["v"]["vendorId"], "name": r["v"]["name"]},
                "part": {"num": part, "description": d["description"], "uom": d["uom"]},
                "qty": r["qty"], "unitCost": r["unit"], "amount": round(r["qty"] * r["unit"], 2),
                "currency": "THB", "ref": {"packSlip": str(pack), "packLine": 1, "poNum": r["poNum"]},
                "meta": {"classId": cat},
            })
        if random.random() < 0.8:
            inv += 1
            transactions.append({
                "_id": "{}|APINV|{}|{}|1".format(COMPANY, r["v"]["vendorNum"], inv),
                "docType": "AP_INVOICE_LINE", "company": COMPANY,
                "date": r["date"] + dt.timedelta(days=random.randint(20, 90)),
                "vendor": {"num": r["v"]["vendorNum"], "id": r["v"]["vendorId"], "name": r["v"]["name"]},
                "part": {"num": part, "description": d["description"], "uom": d["uom"]},
                "qty": r["qty"], "unitCost": r["unit"], "amount": round(r["qty"] * r["unit"], 2),
                "currency": "THB", "ref": {"invoiceNum": str(inv), "invoiceLine": 1, "poNum": r["poNum"]},
                "meta": {"classId": cat},
            })

    # ---- items
    costs = [r["unit"] for r in po_rows]
    mn, mx = min(costs), max(costs)
    by_v = {}
    for r in po_rows:
        b = by_v.setdefault(r["v"]["vendorNum"], {"rows": [], "v": r["v"]})
        b["rows"].append(r)

    v_summary = []
    for vnum, b in sorted(by_v.items(), key=lambda kv: -sum(x["qty"] * x["unit"] for x in kv[1]["rows"])):
        cs = [x["unit"] for x in b["rows"]]
        v_summary.append({
            "vendorNum": vnum, "vendorId": b["v"]["vendorId"], "name": b["v"]["name"],
            "times": len(b["rows"]), "qty": round(sum(x["qty"] for x in b["rows"]), 4),
            "amount": round(sum(x["qty"] * x["unit"] for x in b["rows"]), 2),
            "minUnitCost": round(min(cs), 6), "maxUnitCost": round(max(cs), 6),
            "avgUnitCost": round(sum(cs) / len(cs), 6),
            "lastBuyDate": max(x["date"] for x in b["rows"]),
        })

    items.append({
        "_id": "{}|{}".format(COMPANY, part),
        "company": COMPANY, "partNum": part, "description": d["description"],
        "uom": d["uom"], "classId": cat, "typeCode": "P", "inCatalog": True,
        "stats": {
            "timesOrdered": len(po_rows), "poCount": len({r["poNum"] for r in po_rows}),
            "vendorCount": len(by_v),
            "totalQty": round(sum(r["qty"] for r in po_rows), 4),
            "totalAmount": round(sum(r["qty"] * r["unit"] for r in po_rows), 2),
            "minUnitCost": round(mn, 6), "maxUnitCost": round(mx, 6),
            "avgUnitCost": round(sum(costs) / len(costs), 6),
            "priceSpreadRatio": round(mx / mn, 2),
            "firstBuyDate": min(r["date"] for r in po_rows),
            "lastBuyDate": max(r["date"] for r in po_rows),
        },
        "vendors": v_summary,
        "flags": {
            "noPartNum": False, "singleSource": len(by_v) == 1,
            "priceVolatile": mx / mn >= 2 and len(po_rows) >= 3,
            "service": part.startswith("03"),
        },
    })

    # ---- item_last_price
    ordered = sorted(po_rows, key=lambda r: (r["date"], r["poNum"]))
    last_r = ordered[-1]
    low_r = min(po_rows, key=lambda r: r["unit"])
    high_r = max(po_rows, key=lambda r: r["unit"])

    def point(r):
        return {"unitCost": round(r["unit"], 6), "date": r["date"], "qty": r["qty"],
                "currency": "THB", "poNum": r["poNum"], "poLine": r["poLine"],
                "vendorNum": r["v"]["vendorNum"], "vendorId": r["v"]["vendorId"],
                "vendorName": r["v"]["name"]}

    lp_vendors = []
    for vnum, b in by_v.items():
        rows = sorted(b["rows"], key=lambda r: (r["date"], r["poNum"]))
        cs = [x["unit"] for x in rows]
        lp_vendors.append({
            "vendorNum": vnum, "vendorId": b["v"]["vendorId"], "name": b["v"]["name"],
            "times": len(rows), "lastUnitCost": round(rows[-1]["unit"], 6),
            "lastDate": rows[-1]["date"], "lastPoNum": rows[-1]["poNum"],
            "minUnitCost": round(min(cs), 6), "maxUnitCost": round(max(cs), 6),
            "avgUnitCost": round(sum(cs) / len(cs), 6), "currency": "THB",
        })
    lp_vendors.sort(key=lambda x: x["lastDate"], reverse=True)

    last_price.append({
        "_id": "{}|{}".format(COMPANY, part),
        "company": COMPANY, "partNum": part, "description": d["description"],
        "uom": d["uom"], "classId": cat,
        "last": point(last_r), "lowest": point(low_r), "highest": point(high_r),
        "pricedTimes": len(po_rows), "vendorCount": len(by_v),
        "avgUnitCost": round(sum(costs) / len(costs), 6),
        "spreadRatio": round(mx / mn, 4),
        "lastVsLowestPct": round((last_r["unit"] - mn) / mn * 100, 2),
        "lastVsHighestPct": round((last_r["unit"] - mx) / mx * 100, 2),
        "currencies": ["THB"], "multiCurrency": False,
        "singleSource": len(by_v) == 1, "vendors": lp_vendors,
    })

# ------------------------------------------------------------------ vendor docs
vendor_docs = []
for v in vendor_rows:
    vnum = v["vendorNum"]
    my_tx = [t for t in transactions if t["vendor"]["num"] == vnum]
    po = [t for t in my_tx if t["docType"] == "PO_LINE"]
    rc = [t for t in my_tx if t["docType"] == "RECEIPT_LINE"]
    ap = [t for t in my_tx if t["docType"] == "AP_INVOICE_LINE"]

    top = {}
    for t in po:
        b = top.setdefault(t["part"]["num"], {"partNum": t["part"]["num"], "times": 0, "qty": 0.0, "amount": 0.0})
        b["times"] += 1
        b["qty"] += t["qty"]
        b["amount"] += t["amount"]
    top_parts = sorted(top.values(), key=lambda x: -x["amount"])[:10]

    slug = "".join(ch for ch in v["name"].lower() if ch.isalnum())[:14] or "vendor"

    # ของจริงมีผู้ติดต่อรายบุคคลแค่ ~2,000 คน ต่อผู้ขาย ~1,959 ราย
    # แปลว่าหลายรายไม่มีเลย มีแต่อีเมลบนทะเบียนผู้ขาย และบางรายไม่มีอะไรเลย
    # (ETL ใส่ "-" แทนค่าว่าง) จึงจำลองทั้งสามแบบไว้ทดสอบ
    kind = random.choices(["person", "company_only", "none"], weights=[55, 35, 10], k=1)[0]
    contacts = []
    if kind == "person":
        contacts.append({
            "name": random.choice(["คุณสมชาย ใจดี", "คุณวราภรณ์ ศรีสุข", "K. Nattapong",
                                   "คุณปิยะ พงศ์ไพบูลย์", "Ms. Wanida C.", "คุณธนภัทร อินทร์แก้ว"]),
            "email": "sales@{}.co.th".format(slug),
            "phone": "02-{:03d}-{:04d}".format(random.randint(100, 999), random.randint(1000, 9999)),
            "function": random.choice(["Sales", "Technical", "Account"]),
        })
        if random.random() < 0.4:
            contacts.append({"name": "คุณอรทัย บัวทอง", "email": "support@{}.co.th".format(slug),
                             "phone": "02-{:03d}-{:04d}".format(random.randint(100, 999),
                                                                random.randint(1000, 9999)),
                             "function": "Support"})

    doc = {
        "_id": "{}|{}".format(COMPANY, v["vendorId"]),
        "company": COMPANY, "vendorNum": vnum, "vendorId": v["vendorId"], "name": v["name"],
        "address": {"line1": "{}/{} หมู่ {}".format(random.randint(1, 999), random.randint(1, 99), random.randint(1, 20)),
                    "city": random.choice(["เขตบางรัก", "อำเภอปากเกร็ด", "เขตจตุจักร", "อำเภอบางพลี"]),
                    "state": random.choice(["กรุงเทพมหานคร", "จังหวัดนนทบุรี", "จังหวัดสมุทรปราการ"]),
                    "zip": str(random.randint(10100, 10900)), "country": "Thailand"},
        "contact": (
            {"email": "info@{}.co.th".format(slug),
             "phone": "02-{:03d}-{:04d}".format(random.randint(100, 999), random.randint(1000, 9999))}
            if kind == "company_only" else
            {"email": "-", "phone": "-"} if kind == "none" else
            {"email": contacts[0]["email"], "phone": contacts[0]["phone"]}
        ),
        "currency": "THB", "termsCode": random.choice(["N30", "N60", "COD"]),
        "groupCode": random.choice(["1", "2", "LOC"]),
        "taxId": "0{:012d}".format(random.randint(1, 999999999999)),
        "inactive": random.random() < 0.05,
        "contacts": contacts or None,
        "hasPurchase": bool(po),
    }
    stats = {}
    if po:
        stats["po"] = {"count": len({t["ref"]["poNum"] for t in po}), "lineCount": len(po),
                       "qty": round(sum(t["qty"] for t in po), 4),
                       "amount": round(sum(t["amount"] for t in po), 2),
                       "distinctParts": len({t["part"]["num"] for t in po}),
                       "firstDate": min(t["date"] for t in po), "lastDate": max(t["date"] for t in po)}
    if ap:
        stats["invoice"] = {"lineCount": len(ap), "invoiceCount": len({t["ref"]["invoiceNum"] for t in ap}),
                            "amount": round(sum(t["amount"] for t in ap), 2),
                            "firstDate": min(t["date"] for t in ap), "lastDate": max(t["date"] for t in ap)}
    if rc:
        stats["receipt"] = {"lineCount": len(rc), "count": len({t["ref"]["packSlip"] for t in rc}),
                            "qty": round(sum(t["qty"] for t in rc), 4),
                            "lastDate": max(t["date"] for t in rc)}
    if top_parts:
        stats["topParts"] = [{k: (round(v2, 2) if isinstance(v2, float) else v2) for k, v2 in p.items()}
                             for p in top_parts]
    if stats:
        doc["stats"] = stats
    vendor_docs.append(doc)

# ------------------------------------------------------------------ deliveries
# จำลอง "งวดส่งของ" (PO Release) ตาม docs/delivery_date.md
# ผู้ขายแต่ละรายมีนิสัยการส่งต่างกัน เพื่อให้ทดสอบการจัดอันดับได้จริง
GRACE_DAYS = 0
deliveries, vendor_delivery = [], []

# นิสัยการส่งของแต่ละราย: (ช้าเฉลี่ยกี่วัน, ความแกว่ง)
habit = {}
for v in vendor_rows:
    habit[v["vendorNum"]] = random.choice([
        (-3, 2),    # ส่งก่อนกำหนดประจำ
        (0, 1),     # ตรงเวลาเป๊ะ
        (2, 3),     # ช้านิดหน่อย
        (12, 15),   # ช้าประจำ
        (45, 60),   # ช้ามาก
    ])

po_lines = [t for t in transactions if t["docType"] == "PO_LINE"]
for t in po_lines:
    vnum = t["vendor"]["num"]
    mean, spread = habit[vnum]
    n_rel = random.choices([1, 1, 1, 2, 3], k=1)[0]      # บางบรรทัดแบ่งส่งหลายงวด
    for rel in range(1, n_rel + 1):
        order_date = t["date"]
        promise = order_date + dt.timedelta(days=random.randint(21, 90) + (rel - 1) * 30)
        has_promise_dt = random.random() < 0.72
        rel_qty = round(t["qty"] / n_rel, 2)
        value = round(rel_qty * t["unitCost"], 2)

        rescheduled = random.random() < 0.07
        pushed = random.randint(7, 60) if rescheduled else 0
        original_promise = promise - dt.timedelta(days=pushed) if rescheduled else promise

        # ~13% ยังไม่ได้รับของ (ตรงกับสัดส่วนในรายงานจริง)
        delivered = random.random() > 0.13
        if delivered:
            days_late = int(round(random.gauss(mean, spread)))
            last_receipt = promise + dt.timedelta(days=days_late)
            first_receipt = last_receipt - dt.timedelta(days=random.randint(0, 3))
            on_time = days_late <= GRACE_DAYS
            complete = random.random() < 0.93
            received = rel_qty if complete else round(rel_qty * random.uniform(0.4, 0.95), 2)
            if days_late < -7:
                status_label = "ส่งก่อนกำหนดเกิน 7 วัน"
            elif on_time:
                status_label = "ตรงเวลา"
            elif days_late <= 7:
                status_label = "ช้า 1-7 วัน"
            elif days_late <= 30:
                status_label = "ช้า 8-30 วัน"
            else:
                status_label = "ช้าเกิน 30 วัน"
            overdue, days_overdue = False, None
        else:
            days_late = last_receipt = first_receipt = None
            on_time, complete, received = False, False, 0.0
            status_label = "ยังไม่ได้รับของ"
            overdue = promise < NOW
            days_overdue = (NOW - promise).days if overdue else None

        deliveries.append({
            "_id": "{}|REL|{}|{}|{}".format(COMPANY, t["ref"]["poNum"], t["ref"]["poLine"], rel),
            "company": COMPANY,
            "poNum": t["ref"]["poNum"], "poLine": t["ref"]["poLine"], "poRelNum": rel,
            "vendor": dict(t["vendor"]),
            "part": {"num": t["part"]["num"], "description": t["part"]["description"]},
            "orderDate": order_date,
            "promiseDate": promise,
            "promiseSource": "PromiseDt" if has_promise_dt else "DueDate",
            "dueDate": promise,
            "firstReceiptDate": first_receipt,
            "lastReceiptDate": last_receipt,
            "qty": {"released": rel_qty, "received": received, "complete": complete},
            "value": value,
            "delivered": delivered,
            "onTime": bool(on_time),
            "daysLate": days_late,
            "overdue": overdue,
            "daysOverdue": days_overdue,
            "rescheduled": rescheduled,
            "daysLateVsOriginal": (
                (last_receipt - original_promise).days
                if delivered and rescheduled else None
            ),
            "status": status_label,
        })

# ---- สรุปรายผู้ขาย
by_vendor = {}
for d in deliveries:
    vid = d["vendor"]["id"]
    e = by_vendor.setdefault(vid, {
        "vendorNum": d["vendor"]["num"], "vendorId": vid, "name": d["vendor"]["name"],
        "releases": 0, "onTime": 0, "late": 0, "days": [], "lateValue": 0.0,
        "totalValue": 0.0, "overdue": 0, "first": None, "last": None,
    })
    e["totalValue"] += d["value"]
    if d["overdue"]:
        e["overdue"] += 1
    if not d["delivered"] or d["daysLate"] is None:
        continue
    e["releases"] += 1
    e["days"].append(d["daysLate"])
    if d["onTime"]:
        e["onTime"] += 1
    else:
        e["late"] += 1
        e["lateValue"] += d["value"]
    for key, fn in (("first", min), ("last", max)):
        cur = e[key]
        e[key] = d["lastReceiptDate"] if cur is None else fn(cur, d["lastReceiptDate"])

for vid, e in by_vendor.items():
    days = sorted(e["days"])
    if not days:
        continue
    mid = len(days) // 2
    median = days[mid] if len(days) % 2 else (days[mid - 1] + days[mid]) / 2
    vendor_delivery.append({
        "_id": "{}|{}".format(COMPANY, vid),
        "company": COMPANY, "vendorNum": e["vendorNum"], "vendorId": vid, "name": e["name"],
        "releases": e["releases"], "onTime": e["onTime"], "late": e["late"],
        "otdPct": round(e["onTime"] * 100 / e["releases"], 1),
        "avgDaysLate": round(sum(days) / len(days), 2),
        "medianDaysLate": median,
        "maxDaysLate": max(days),
        "lateValue": round(e["lateValue"], 2), "totalValue": round(e["totalValue"], 2),
        "overdueReleases": e["overdue"],
        "firstDelivery": e["first"], "lastDelivery": e["last"],
    })

# ------------------------------------------------------------------ write
etl_run = {"startedAt": dt.datetime(2026, 8, 15, 14, 23, 30),
           "finishedAt": dt.datetime(2026, 8, 15, 14, 30, 40), "mode": "reload",
           "counts": {"vendors": len(vendor_docs), "items": len(items),
                      "item_last_price": len(last_price), "transactions": len(transactions)}}

if DUMP_ONLY:
    with open(SEED_FILE, "wb") as fh:
        pickle.dump({"vendors": vendor_docs, "items": items, "item_last_price": last_price,
                     "transactions": transactions, "etl_runs": [etl_run],
                     "deliveries": deliveries, "vendor_delivery": vendor_delivery}, fh)
    print("dumped " + SEED_FILE)
    sys.exit(0)

db.vendors.insert_many(vendor_docs)
db.items.insert_many(items)
db.item_last_price.insert_many(last_price)
db.transactions.insert_many(transactions)
db.etl_runs.insert_one(etl_run)
db.deliveries.insert_many(deliveries)
db.vendor_delivery.insert_many(vendor_delivery)
print("seeded")
