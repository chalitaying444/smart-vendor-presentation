"""ตรวจ API ทั้งชุดด้วยเงื่อนไขที่ผู้ใช้ขอไว้"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import BASE, FRONTEND, token       # noqa: E402

TOK = token()
ok = fail = 0


def call(path, method="GET", body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")


def status_of(path):
    """ใช้กับ endpoint ที่คืนไฟล์ ไม่ใช่ JSON"""
    req = urllib.request.Request(
        BASE + path, headers={"Authorization": "Bearer " + TOK})
    try:
        with urllib.request.urlopen(req) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        e.read()
        return e.code


def raw(path, token=None):
    """เรียก endpoint ที่คืนไฟล์ — คืน (status, headers, bytes)"""
    headers = {"Authorization": "Bearer " + (token or TOK)} if token != "" else {}
    req = urllib.request.Request(BASE + path, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def upload(path, filename, content, content_type="application/pdf"):
    """ยิง multipart/form-data เองเพราะ urllib ไม่มีให้"""
    boundary = "----vendorapptest"
    body = b"".join([
        ("--%s\r\n" % boundary).encode(),
        ('Content-Disposition: form-data; name="file"; filename="%s"\r\n' % filename).encode(),
        ("Content-Type: %s\r\n\r\n" % content_type).encode(),
        content,
        ("\r\n--%s--\r\n" % boundary).encode(),
    ])
    req = urllib.request.Request(
        BASE + path, method="POST", data=body,
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print("PASS", label)
    else:
        fail += 1
        print("FAIL", label, extra)


# ------------------------------------------------------- ค้นหาสินค้าแบบยืดหยุ่น
s, all_items = call("/catalog/items?limit=5")
check("เปิดหน้าสินค้าแล้วเห็นรายการทันที (ไม่ต้องพิมพ์อะไร)",
      s == 200 and all_items["total"] > 0 and len(all_items["items"]) == 5, all_items)

first = all_items["items"][0]
part = first["part_num"]

s, r = call("/catalog/items?q=" + part.replace("-", ""))
check("พิมพ์รหัสไม่มีขีดก็เจอ ({})".format(part.replace("-", "")),
      s == 200 and any(i["part_num"] == part for i in r["items"]), r.get("total"))

s, r = call("/catalog/items?q=ethernet%20switch")
check("ค้นด้วยคำอธิบายภาษาอังกฤษ", s == 200 and r["total"] > 0
      and all("ETHERNET" in i["description"].upper() for i in r["items"][:3]), r.get("total"))

s, r = call("/catalog/items?q=ethernett%20swich")
check("สะกดผิดยังเจอ (fuzzy)", s == 200 and r["total"] > 0, (r.get("total"), r.get("fuzzy_terms")))

s, r = call("/catalog/items?q=firewall%20moxa")
check("หลายคำ เจอคนละที่ (สินค้า + ผู้ขาย)", s == 200 and r["total"] > 0, r.get("total"))

s, r = call("/catalog/items?q=" + part)
check("ค้นรหัสเป๊ะ ได้อันดับ 1", s == 200 and r["items"][0]["part_num"] == part)

s, r = call("/catalog/items?q=zzzzqqqqxxxx")
check("ค้นไม่เจอ คืนผลว่างอย่างสุภาพ ไม่ error", s == 200 and r["total"] == 0)

s, r = call("/catalog/items?price_volatile=true&limit=5")
check("กรองเฉพาะสินค้าที่ราคาแกว่ง", s == 200 and all(i["price_volatile"] for i in r["items"]))

s, r = call("/catalog/items?single_source=true&limit=5")
check("กรองเฉพาะสินค้าที่มีผู้ขายรายเดียว", s == 200 and all(i["single_source"] for i in r["items"]))

# ------------------------------------------------------- ราคาล่าสุด
s, item = call("/catalog/items/" + part)
check("เปิดสินค้าได้", s == 200 and item["part_num"] == part, item)
price = item.get("price") or {}
check("มีราคาล่าสุด พร้อมวันที่และผู้ขาย",
      bool(price.get("last", {}).get("unit_cost")) and bool(price["last"].get("date"))
      and bool(price["last"].get("vendor_name")), price.get("last"))
check("มีราคาต่ำสุด/สูงสุดให้เทียบ",
      price.get("lowest", {}).get("unit_cost") is not None
      and price.get("highest", {}).get("unit_cost") is not None)
check("ราคาต่ำสุด <= ราคาล่าสุด <= ราคาสูงสุด",
      price["lowest"]["unit_cost"] <= price["highest"]["unit_cost"]
      and price["lowest"]["unit_cost"] <= price["last"]["unit_cost"] <= price["highest"]["unit_cost"])

vendors = item.get("vendors") or []
check("เห็นผู้ขายทุกรายที่เคยขายสินค้านี้ พร้อมราคาล่าสุดของแต่ละราย",
      len(vendors) > 0 and all("last_unit_cost" in v for v in vendors), vendors[:1])
check("ผู้ขายเรียงจากราคาล่าสุดถูกสุดก่อน",
      [v["last_unit_cost"] for v in vendors if v["last_unit_cost"] is not None]
      == sorted([v["last_unit_cost"] for v in vendors if v["last_unit_cost"] is not None]))
check("ผู้ขายมี vendor_key ใช้ยิง RFQ ได้เลย",
      all(v["vendor_key"].startswith("epicor:") for v in vendors))

# ------------------------------------------------------- transaction ของ item
s, tx = call("/catalog/items/{}/transactions?limit=10".format(part))
check("เรียก transaction ของสินค้าได้", s == 200 and tx["total"] > 0, tx.get("total"))
check("transaction มีทั้งวันที่ ผู้ขาย จำนวน ราคาต่อหน่วย และมูลค่า",
      all(t.get("date") and t.get("vendor_name") and t.get("qty") is not None
          and t.get("unit_cost") is not None and t.get("amount") is not None
          for t in tx["items"]), tx["items"][:1])
check("transaction เรียงจากล่าสุดก่อน",
      [t["date"] for t in tx["items"]] == sorted([t["date"] for t in tx["items"]], reverse=True))
check("มีสรุปแยกตามชนิดเอกสาร (สั่งซื้อ/รับของ/ใบแจ้งหนี้)",
      len(tx.get("summary") or []) >= 1
      and all(x.get("doc_type_label") for x in tx["summary"]), tx.get("summary"))

s, tx_po = call("/catalog/items/{}/transactions?doc_type=PO_LINE&limit=5".format(part))
check("กรอง transaction เฉพาะใบสั่งซื้อได้",
      s == 200 and all(t["doc_type"] == "PO_LINE" for t in tx_po["items"]))

s, tx_bad = call("/catalog/items/{}/transactions?doc_type=NOPE".format(part))
check("doc_type ผิด คืน 400 พร้อมข้อความอธิบาย", tx_bad and s == 400, (s, tx_bad))

s, hist = call("/catalog/items/{}/price-history".format(part))
check("มีประวัติราคาไว้วาดกราฟ", s == 200 and len(hist["points"]) > 0)
check("ประวัติราคาเรียงตามเวลา",
      [p["date"] for p in hist["points"]] == sorted(p["date"] for p in hist["points"]))

# ------------------------------------------------------- ผู้ขาย
s, vs = call("/vendors?limit=5")
check("รายชื่อผู้ขายมาจาก Epicor", s == 200 and vs["total"] > 0, vs.get("total"))
vkey = vs["items"][0]["vendor_key"]
vid = vs["items"][0]["vendor_id"]

s, v = call("/vendors/" + vkey)
check("เปิดผู้ขายด้วย vendor_key ได้", s == 200 and v["vendor_id"] == vid)
s, v2 = call("/vendors/" + vid)
check("เปิดผู้ขายด้วยรหัสเปล่า ๆ ก็ได้ (ลิงก์เก่าไม่พัง)", s == 200 and v2["vendor_id"] == vid)

s, vitems = call("/vendors/{}/items?limit=5".format(vkey))
check("เห็นสินค้าที่ผู้ขายรายนี้เคยขาย พร้อมราคาล่าสุดของรายนี้",
      s == 200 and vitems["total"] > 0
      and any(i.get("vendor_last_price") is not None for i in vitems["items"]),
      vitems.get("total"))

s, vtx = call("/vendors/{}/transactions?limit=5".format(vkey))
check("เห็น transaction ของผู้ขายรายนี้", s == 200 and vtx["total"] > 0)

s, ov = call("/catalog/overview")
check("หน้าภาพรวมมีตัวเลขครบ",
      s == 200 and ov["counts"]["items"] > 0 and len(ov["top_vendors"]) > 0
      and len(ov["top_items"]) > 0)

# ------------------------------------------------------- RFQ
s, det = call("/catalog/items/" + part)
picked = [v["vendor_key"] for v in det["vendors"][:3]]
s, rfq = call("/rfqs", "POST", {
    "title": "ขอราคา " + det["description"][:40],
    "currency": "THB",
    "lines": [{"part_num": part, "qty": 10}],
    "vendor_keys": picked,
})
check("สร้าง RFQ จากรหัสสินค้าได้ทันที (ไม่ต้องเพิ่มสินค้าเข้าระบบก่อน)", s == 201, rfq)
rid = rfq["id"]
check("บรรทัด RFQ พกราคาล่าสุดไปด้วย", rfq["lines"][0].get("last_price") is not None,
      rfq["lines"][0])
check("เชิญผู้ขายครบตามที่เลือก", len(rfq["invites"]) == len(picked))

s, sug = call("/rfqs/{}/suggested-vendors".format(rid))
check("แนะนำผู้ขายจากประวัติการซื้อจริง",
      s == 200 and len(sug["vendors"]) > 0
      and all(v["covered_items"] > 0 for v in sug["vendors"]), sug)

s, sent = call("/rfqs/{}/send".format(rid), "POST", {"message": "รบกวนเสนอราคาภายในสัปดาห์นี้"})
check("ส่ง RFQ ออกได้ + ได้ลิงก์ portal", s == 200 and sent["sent"] == len(picked)
      and all(i["portal_url"] for i in sent["invites"]), sent)

# ลิงก์ที่ส่งให้ผู้ขายต้องสร้างจาก FRONTEND_URL เสมอ — ตอนเปิดผ่าน ngrok
# ค่านี้จะเป็น URL ของ ngrok ถ้าไปฮาร์ดโค้ด localhost ไว้ ผู้ขายจะได้ลิงก์ที่เปิดไม่ได้
check("ลิงก์ portal สร้างจาก FRONTEND_URL ไม่ใช่ค่าที่ฝังไว้ในโค้ด",
      all(i["portal_url"].startswith(FRONTEND + "/portal/") for i in sent["invites"]),
      sent["invites"][0].get("portal_url"))

token = sent["invites"][0]["token"]
s, pv = call("/portal/{}".format(token))
check("เปิดลิงก์ครั้งแรก ระบบยังไม่ปล่อยเนื้อหาใบขอราคา", s == 200 and pv.get("locked") is True, pv)
check("ยังไม่รับทราบ = ไม่มีรายการสินค้าติดมาใน response เลย",
      "lines" not in pv and "title" not in pv, list(pv.keys()))
raw_locked = json.dumps(pv, ensure_ascii=False)
check("ยังไม่รับทราบ = ชื่อ/รหัสสินค้าไม่หลุดออกไป",
      part not in raw_locked and "vendor" not in pv, raw_locked[:300])
check("แต่ยังบอกได้ว่าเป็นใบไหน กี่รายการ ส่งเมื่อไหร่",
      pv.get("rfq_no") and pv.get("line_count") == 1 and "due_date" in pv, pv)
check("หน้าผู้ขายส่งเงื่อนไขที่ต้องรับทราบมาด้วย",
      len(pv.get("terms") or []) >= 5 and pv.get("terms_version"), pv.get("terms_version"))
check("ยังไม่รับทราบ สถานะเป็นว่าง", pv.get("terms_accepted_at") is None)
check("ผู้ขายไม่เห็นราคาเดิมของเรา (ข้อมูลภายในไม่รั่ว)",
      "last_price" not in raw_locked, "portal ส่ง last_price ออกไปด้วย")

# ไฟล์ Excel มีรายการครบ ถ้าไม่กันด้วย การซ่อนบนหน้าจอก็ไม่มีความหมาย
s = status_of("/portal/{}/document".format(token))
check("ยังไม่รับทราบเงื่อนไข โหลดไฟล์ใบขอราคาไม่ได้", s == 403, s)

# หน้าเสนอราคาบังคับให้กดรับทราบเงื่อนไขก่อน จึงต้องทำขั้นนี้ก่อนส่งราคา
s, blocked = call("/portal/{}/quote".format(sent["invites"][0]["token"]), "POST", {
    "lines": [{"part_num": part, "unit_price": 1}], "currency": "THB"})
check("ยังไม่รับทราบเงื่อนไข ส่งราคาไม่ได้ (กันไว้ฝั่งเซิร์ฟเวอร์)", s == 403, (s, blocked))

s, bad_accept = call("/portal/{}/accept-terms".format(sent["invites"][0]["token"]), "POST",
                     {"accepted": False})
check("ติ๊กไม่ยอมรับ ระบบไม่บันทึกให้", s == 400, (s, bad_accept))

call("/portal/{}/accept-terms".format(token), "POST", {"accepted": True, "accepted_by": "ผู้จัดการ"})
s, pv2 = call("/portal/{}".format(token))
check("กดรับทราบแล้ว ข้อมูลจึงเปิดให้เห็น",
      s == 200 and pv2.get("locked") is False and pv2["lines"][0]["part_num"] == part, pv2)
check("บันทึกเวลา/เวอร์ชัน/ชื่อผู้รับทราบไว้",
      pv2.get("terms_accepted_at") and pv2.get("terms_accepted_version"), pv2.get("terms_accepted_at"))
s = status_of("/portal/{}/document".format(token))
check("รับทราบแล้วจึงโหลดไฟล์ใบขอราคาได้", s == 200, s)

# ------------------------------------------------------- ไฟล์เก็บใน MongoDB ไม่ใช่ดิสก์
import hashlib
import os

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "vendor_app", "backend", "uploads")


def disk_files():
    """นับไฟล์ในโฟลเดอร์ uploads — ต้องไม่เพิ่มขึ้นเลยหลังอัปโหลด"""
    total = []
    for root, _dirs, names in os.walk(UPLOAD_DIR):
        total += [os.path.join(root, n) for n in names if not n.startswith(".")]
    return set(total)


before_disk = disk_files()

st, headers, xlsx = raw("/portal/{}/document".format(token))
check("ใบขอราคาที่โหลดได้เป็นไฟล์ Excel จริง (ไม่ใช่หน้า error)",
      st == 200 and xlsx[:2] == b"PK" and len(xlsx) > 3000, (st, len(xlsx)))
check("ส่งชื่อไฟล์กลับมาให้เบราว์เซอร์ตั้งชื่อถูก",
      "filename" in headers.get("content-disposition", ""), headers.get("content-disposition"))

# ไฟล์แนบจากผู้ขาย — ชื่อไทยและใหญ่กว่า 1 ก้อน เพื่อพิสูจน์เรื่องการตัดก้อน
thai_name = "ใบเสนอราคา_บริษัททดสอบ.pdf"
small = "%PDF-1.4 ทดสอบไฟล์เล็ก".encode("utf-8").ljust(2048, b"x")
st, up = upload("/portal/{}/attachments".format(token), thai_name, small)
check("ผู้ขายแนบไฟล์ได้", st == 201 and up["attachment"]["file_id"], (st, up))
check("ไม่มี path บนดิสก์ติดกลับมาในข้อมูลไฟล์แนบอีกแล้ว",
      "path" not in up["attachment"] and "relative_path" not in up["attachment"]
      and "stored_name" not in up["attachment"], up["attachment"])
check("เก็บ sha256 ไว้ตรวจความถูกต้องของไฟล์",
      up["attachment"]["sha256"] == hashlib.sha256(small).hexdigest(), up["attachment"].get("sha256"))
fid = up["attachment"]["file_id"]

check("อัปโหลดแล้วไม่มีไฟล์ใหม่โผล่บนดิสก์เลย",
      disk_files() == before_disk, sorted(disk_files() - before_disk)[:3])

st, headers, got = raw(up["attachment"]["url"].replace("/api", "", 1), token="")
check("ผู้ขายเปิดไฟล์ที่ตัวเองแนบได้ และได้ไฟล์เดิมทุกไบต์",
      st == 200 and got == small, (st, len(got)))
check("ชื่อไฟล์ภาษาไทยส่งกลับได้ ไม่เพี้ยนและไม่พัง",
      "filename*=UTF-8''" in headers.get("content-disposition", ""),
      headers.get("content-disposition"))

# ไฟล์ใหญ่กว่า 1 ก้อน (ก้อนละ 1 MB) — ต้องประกอบกลับมาได้เป๊ะและเรียงถูก
big = bytes(bytearray((i * 7919) % 256 for i in range(2_500_000)))
st, up_big = upload("/portal/{}/attachments".format(token), "ใบเสนอราคาใหญ่.pdf", big)
check("ไฟล์ใหญ่กว่า 1 MB อัปโหลดได้", st == 201, st)
st, _h, got_big = raw(up_big["attachment"]["url"].replace("/api", "", 1), token="")
check("ไฟล์หลายก้อนประกอบกลับมาครบและเรียงถูกต้อง",
      st == 200 and got_big == big, (st, len(got_big), len(big)))

# ฝั่งผู้ซื้อต้องเปิดไฟล์ที่ผู้ขายแนบมาได้ (เดิมเห็นแค่จำนวน)
st, _h, buyer_got = raw("/files/{}".format(fid))
check("ผู้ซื้อที่ล็อกอินแล้วเปิดไฟล์แนบได้", st == 200 and buyer_got == small, st)
st, _h, _b = raw("/files/{}".format(fid), token="")
check("ไม่ได้ล็อกอิน โหลดไฟล์ไม่ได้ (ของเดิมเปิดสาธารณะทุกคน)", st in (401, 403), st)

s, cmp_view = call("/rfqs/{}/comparison".format(rid))
me = [v for v in cmp_view["vendors"] if v["vendor_key"] == sent["invites"][0]["vendor_key"]]
check("ตารางเทียบราคาส่งลิงก์ไฟล์แนบมาให้ด้วย ไม่ใช่แค่จำนวน",
      me and len(me[0]["attachments"]) == 2
      and all(a["url"].startswith("/api/files/") for a in me[0]["attachments"]),
      me[0]["attachments"] if me else None)

# ผู้ขายรายอื่นต้องเปิดไฟล์ของคนอื่นไม่ได้ แม้จะรู้ id
other_token = sent["invites"][1]["token"]
call("/portal/{}/accept-terms".format(other_token), "POST", {"accepted": True})
st, _h, _b = raw("/portal/{}/attachments/{}".format(other_token, fid), token="")
check("ผู้ขายรายอื่นเปิดไฟล์ของคู่แข่งไม่ได้ แม้รู้ id", st == 404, st)

s, del_res = call("/portal/{}/attachments/{}".format(token, fid), "DELETE")
check("ลบไฟล์แนบได้", s == 200 and len(del_res["attachments"]) == 1, del_res)
st, _h, _b = raw("/files/{}".format(fid))
check("ลบแล้วเนื้อไฟล์หายจากฐานข้อมูลจริง ไม่ได้แค่ถอดชื่อออก", st == 404, st)

st, bad = upload("/portal/{}/attachments".format(token), "ไฟล์อันตราย.exe", b"MZ")
check("นามสกุลที่ไม่รองรับ อัปโหลดไม่ได้", st == 400 and ".exe" in str(bad.get("detail", "")), bad)
st, empty = upload("/portal/{}/attachments".format(token), "ว่าง.pdf", b"")
check("ไฟล์ว่าง อัปโหลดไม่ได้", st == 400, empty)

st, _h, _b = raw("/files/000000000000000000000000")
check("ขอไฟล์ที่ไม่มีอยู่ คืน 404 ไม่ใช่ 500", st == 404, st)
st, _h, _b = raw("/files/not-an-object-id")
check("ขอไฟล์ด้วย id ที่ผิดรูปแบบ ก็คืน 404 ไม่ใช่ error หน้าแตก", st == 404, st)

check("ทั้งชุดนี้ไม่มีไฟล์ใดถูกเขียนลงดิสก์เลย", disk_files() == before_disk,
      sorted(disk_files() - before_disk)[:5])

prices = [900000, 850000, 990000]
for i, inv in enumerate(sent["invites"]):
    call("/portal/{}/accept-terms".format(inv["token"]), "POST",
         {"accepted": True, "accepted_by": "ฝ่ายขาย"})
    s, q = call("/portal/{}/quote".format(inv["token"]), "POST", {
        "lines": [{"part_num": part, "unit_price": prices[i % len(prices)], "lead_time_days": 14 + i}],
        "currency": "THB", "vat_percent": 7, "contact_name": "ฝ่ายขาย",
    })
    if s != 200:
        print("   quote error", s, q)
check("ผู้ขายเสนอราคากลับมาได้ทุกราย",
      call("/rfqs/{}/quotes".format(rid))[1].__len__() == len(picked))

s, cmp_ = call("/rfqs/{}/comparison".format(rid))
check("ตารางเทียบราคาใช้งานได้", s == 200 and len(cmp_["rows"]) == 1
      and len(cmp_["vendors"]) == len(picked))
row = cmp_["rows"][0]
check("ตารางเทียบราคาโชว์ราคาเดิมให้เทียบด้วย", row.get("last_price") is not None, row)
check("คำนวณส่วนต่างกับราคาเดิมให้", row.get("best_vs_last_pct") is not None, row)
check("ไฮไลต์ราคาต่ำสุดถูกต้อง",
      any(c["is_lowest"] for c in row["cells"])
      and min(c["unit_price"] for c in row["cells"] if c["unit_price"] is not None)
      == next(c["unit_price"] for c in row["cells"] if c["is_lowest"]))

s, aw = call("/rfqs/{}/award".format(rid), "POST",
             {"vendor_key": cmp_["best_total_vendor_key"], "reason": "ราคาต่ำสุด"})
check("ประกาศผู้ชนะได้", s == 200 and aw["status"] == "awarded", aw)
check("บันทึกส่วนต่างเทียบราคาเดิมไว้ในผลประกาศ",
      aw["awards"][0].get("vs_last_pct") is not None, aw["awards"][0])



# ------------------------------------------------------- ข้อมูลสรุปที่คำนวณล่วงหน้า
import time as _t

s, ov1 = call("/catalog/overview")
check("หน้าภาพรวมแนบเวลาที่คำนวณมาด้วย",
      s == 200 and ov1.get("snapshot", {}).get("built_at"), ov1.get("snapshot"))
check("บอกด้วยว่ารอบอัปเดตถัดไปเมื่อไร", bool(ov1["snapshot"].get("next_refresh_at")))

t0 = _t.time(); call("/catalog/overview"); cached = _t.time() - t0
t0 = _t.time(); call("/catalog/overview/refresh", "POST"); rebuilt = _t.time() - t0
check("อ่านจากแคชเร็วกว่าคำนวณใหม่", cached < rebuilt,
      "cached={:.3f}s rebuild={:.3f}s".format(cached, rebuilt))

s, ov2 = call("/catalog/overview")
check("กดคำนวณใหม่แล้วเวลาที่คำนวณเปลี่ยนจริง",
      ov2["snapshot"]["built_at"] != ov1["snapshot"]["built_at"],
      (ov1["snapshot"]["built_at"], ov2["snapshot"]["built_at"]))
check("ข้อมูลหลังคำนวณใหม่ยังครบเหมือนเดิม",
      ov2["counts"]["items"] == ov1["counts"]["items"]
      and len(ov2["top_vendors"]) == len(ov1["top_vendors"]))

s, fc = call("/catalog/facets")
check("facets ก็อ่านจากข้อมูลสรุปเช่นกัน",
      s == 200 and fc.get("snapshot", {}).get("built_at") and fc.get("counts"))

import urllib.request as _u
with _u.urlopen(BASE + "/health") as r:
    h = json.loads(r.read().decode())
check("/health บอกสถานะข้อมูลสรุปทุกชุด",
      "catalog.overview" in (h.get("snapshots") or {})
      and h["snapshots"]["catalog.overview"].get("build_seconds") is not None,
      h.get("snapshots"))

# ------------------------------------------------------- ช่องทางติดต่อของผู้ขาย
# Epicor เก็บอีเมลไว้สองที่: รายบุคคล (VendCnt) กับอีเมลกลางบนทะเบียนผู้ขาย
# หลายรายมีแค่อีเมลกลาง ถ้าอ่านแค่รายบุคคลจะกลายเป็น "ไม่มีผู้ติดต่อ" ทั้งที่ติดต่อได้
s, all_v = call("/vendors?limit=200&has_purchase=true")
with_contacts = [v for v in all_v["items"] if v["contact_count"] > 0]
company_only = [v for v in all_v["items"]
                if v["contact_count"] > 0 and all(c["is_company"] for c in v["contacts"])]
no_channel = [v for v in all_v["items"] if v["contact_count"] == 0]

check("ผู้ขายส่วนใหญ่มีช่องทางติดต่อ",
      len(with_contacts) > len(all_v["items"]) * 0.6,
      "{}/{}".format(len(with_contacts), len(all_v["items"])))
check("ผู้ขายที่มีแต่อีเมลกลางของบริษัท ก็ยังมีช่องทางติดต่อให้เห็น",
      len(company_only) > 0, len(company_only))

if company_only:
    v = company_only[0]
    check("อีเมลกลางถูกใช้เป็นผู้ติดต่อหลัก (ใช้ส่ง RFQ ได้)",
          v["contacts"][0]["is_primary"] and bool(v["contacts"][0]["email"]), v["contacts"][0])
    check("ติดธงไว้ว่าเป็นอีเมลบริษัท ไม่ใช่ชื่อคน", v["contacts"][0]["is_company"])
    check("emails ของผู้ขายไม่ว่าง", len(v["emails"]) > 0, v["emails"])

    # เชิญเข้า RFQ แล้วต้องได้อีเมลติดไปด้วย ไม่ใช่ช่องว่าง
    s, rfq2 = call("/rfqs", "POST", {
        "title": "ทดสอบอีเมลผู้ขาย", "currency": "THB",
        "lines": [{"part_num": part, "qty": 1}],
        "vendor_keys": [v["vendor_key"]],
    })
    check("เชิญผู้ขายที่มีแต่อีเมลกลางเข้า RFQ ได้", s == 201, rfq2)
    if s == 201:
        check("ใบเชิญพกอีเมลของผู้ขายไปด้วย",
              rfq2["invites"][0]["contact_email"] == v["emails"][0],
              rfq2["invites"][0].get("contact_email"))
        call("/rfqs/{}".format(rfq2["id"]), "DELETE")

if no_channel:
    v = no_channel[0]
    check("ผู้ขายที่ไม่มีช่องทางติดต่อจริง ๆ คืนค่าว่างตรงไปตรงมา",
          v["emails"] == [] and v["phones"] == [] and v["contacts"] == [], v)

check("ค่าขยะอย่าง '-' ไม่หลุดมาเป็นอีเมล",
      all(e not in ("-", "", "N/A") for v in all_v["items"] for e in v["emails"]))

# ------------------------------------------------------- ความตรงเวลาในการส่ง
s, vlist = call("/vendors?limit=50")
check("รายชื่อผู้ขายพกคะแนนความตรงเวลามาด้วย",
      s == 200 and all("delivery" in v for v in vlist["items"]), vlist["items"][0].keys())

scored = [v for v in vlist["items"] if v["delivery"]["has_data"]]
check("มีผู้ขายที่มีประวัติส่งของจริง", len(scored) > 0, len(scored))

v0 = scored[0]
d0 = v0["delivery"]
check("คะแนนมีครบทั้ง % งวด มัธยฐาน และงวดค้างส่ง",
      d0["otd_pct"] is not None and d0["releases"] > 0
      and "median_days_late" in d0 and "overdue_releases" in d0, d0)
check("% ตรงเวลาอยู่ในช่วง 0-100", all(0 <= v["delivery"]["otd_pct"] <= 100 for v in scored))
check("จำนวนตรงเวลา + ช้า = งวดที่วัดผลได้",
      all(v["delivery"]["on_time"] + v["delivery"]["late"] == v["delivery"]["releases"]
          for v in scored))
check("% คำนวณตรงกับจำนวนงวดจริง",
      all(abs(v["delivery"]["otd_pct"]
              - v["delivery"]["on_time"] * 100 / v["delivery"]["releases"]) < 0.15
          for v in scored))
check("มีคำอธิบายระดับเป็นภาษาคน ไม่ใช่แค่ตัวเลข",
      all(v["delivery"]["label"] and v["delivery"]["level"] for v in scored))
check("ผู้ขายที่งวดน้อยถูกติดธงว่าข้อมูลยังน้อย",
      all(v["delivery"]["reliable"] == (v["delivery"]["releases"] >= 5) for v in scored))

s, late_only = call("/vendors?limit=50&otd_max=70&reliable_only=true")
check("กรองเฉพาะรายที่ส่งตรงเวลาต่ำกว่าเกณฑ์ได้",
      s == 200 and all(v["delivery"]["otd_pct"] <= 70 and v["delivery"]["reliable"]
                       for v in late_only["items"]), late_only.get("total"))

vkey2 = v0["vendor_key"]
s, vdet = call("/vendors/" + vkey2)
check("หน้ารายละเอียดผู้ขายมีคะแนนและสัดส่วนสถานะ",
      s == 200 and vdet["delivery"]["has_data"] and len(vdet["delivery_by_status"]) > 0,
      vdet.get("delivery_by_status"))
check("สัดส่วนสถานะรวมกันได้ 100%",
      abs(sum(x["percent"] for x in vdet["delivery_by_status"]) - 100) < 1.0,
      sum(x["percent"] for x in vdet["delivery_by_status"]))

s, dls = call("/vendors/{}/deliveries?limit=10".format(vkey2))
check("เรียกประวัติการส่งรายงวดได้", s == 200 and dls["total"] > 0, dls.get("total"))
check("แต่ละงวดบอกครบว่าสัญญาไว้เมื่อไร รับจริงเมื่อไร และช้ากี่วัน",
      all(x.get("promise_date") and "days_late" in x and "status" in x
          and x.get("po_num") is not None for x in dls["items"]), dls["items"][:1])
check("บอกด้วยว่าวันกำหนดมาจากผู้ขายรับปากหรือค่าในระบบ",
      all(x["promise_source"] in ("PromiseDt", "DueDate") for x in dls["items"]),
      {x["promise_source"] for x in dls["items"]})

s, late_rel = call("/vendors/{}/deliveries?only_late=true&limit=10".format(vkey2))
check("กรองเฉพาะงวดที่ส่งช้าได้",
      s == 200 and all(x["delivered"] and not x["on_time"] for x in late_rel["items"]))

s, over_rel = call("/vendors/{}/deliveries?only_overdue=true&limit=10".format(vkey2))
check("กรองเฉพาะงวดที่ยังค้างส่งได้",
      s == 200 and all(x["overdue"] and not x["delivered"] for x in over_rel["items"]))
if over_rel["items"]:
    check("งวดค้างส่งบอกจำนวนวันที่ค้างมา",
          all(x["days_overdue"] and x["days_overdue"] > 0 for x in over_rel["items"]))

s, resched = call("/vendors/{}/deliveries?only_rescheduled=true&limit=10".format(vkey2))
check("กรองเฉพาะงวดที่เคยเลื่อนกำหนดได้",
      s == 200 and all(x["rescheduled"] for x in resched["items"]))

# หน้าสินค้า — ต้องเห็นทั้งราคาและความตรงเวลาพร้อมกัน
s, det2 = call("/catalog/items/" + part)
check("ผู้ขายในหน้าสินค้ามีทั้งราคาและคะแนนความตรงเวลา",
      all("delivery" in v and "last_unit_cost" in v for v in det2["vendors"]))
check("มีความตรงเวลาเฉพาะสินค้ารหัสนี้แยกจากคะแนนรวม",
      any(v.get("delivery_this_item") for v in det2["vendors"]),
      [v.get("delivery_this_item") for v in det2["vendors"]][:2])

per_item = [v for v in det2["vendors"] if v.get("delivery_this_item")]
if per_item:
    ti = per_item[0]["delivery_this_item"]
    check("ตัวเลขเฉพาะสินค้าคำนวณถูก",
          abs(ti["otd_pct"] - ti["on_time"] * 100 / ti["releases"]) < 0.15, ti)

check("ผู้ขายที่ระบบแนะนำก็มีคะแนนความตรงเวลา",
      all("delivery" in v for v in det2["suggested_vendors"]))

# หน้าภาพรวม
s, ov3 = call("/catalog/overview/refresh", "POST")
dsum = ov3.get("delivery") or {}
check("หน้าภาพรวมมีสรุปการส่งของทั้งบริษัท", dsum.get("has_data") is True, dsum.get("has_data"))
check("สรุปมี % รวม งวดค้างส่ง และผู้ขายที่ควรตามงาน",
      dsum.get("otd_pct") is not None and "overdue_releases" in dsum
      and len(dsum.get("worst_vendors") or []) > 0, list(dsum.keys()))
check("อันดับผู้ขายนับเฉพาะรายที่มีงวดมากพอ",
      all(v["releases"] >= dsum["min_reliable_releases"] for v in dsum["worst_vendors"]),
      [(v["name"][:12], v["releases"]) for v in dsum["worst_vendors"]][:3])
check("ผู้ขายที่ควรตามงานเรียงจากแย่ที่สุด",
      [v["otd_pct"] for v in dsum["worst_vendors"]]
      == sorted(v["otd_pct"] for v in dsum["worst_vendors"]))
check("รายการงวดค้างส่งเรียงจากค้างนานสุด",
      [d["days_overdue"] for d in dsum["most_overdue"]]
      == sorted((d["days_overdue"] for d in dsum["most_overdue"]), reverse=True))

# ตารางเทียบราคา — ต้องเห็นความตรงเวลาข้างราคา
s, cmp2 = call("/rfqs/{}/comparison".format(rid))
check("ตารางเทียบราคาแนบความตรงเวลาของผู้ขายทุกคอลัมน์",
      s == 200 and all("delivery" in v for v in cmp2["vendors"]), cmp2["vendors"][0].keys())
check("ผลประกาศผู้ชนะบันทึก OTD ณ วันที่ตัดสินไว้ด้วย",
      "vendor_otd_pct" in (aw["awards"][0] if aw.get("awards") else {}), aw.get("awards", [{}])[0])

# ------------------------------------------------------- หน้าตามงานส่งของ
s, ov_list = call("/deliveries?only_overdue=true&limit=20")
check("ค้นงวดค้างส่งข้ามผู้ขายทั้งหมดได้", s == 200 and ov_list["total"] > 0, ov_list.get("total"))
check("งวดค้างส่งทุกแถวยังไม่ได้รับของจริง",
      all(x["overdue"] and not x["delivered"] for x in ov_list["items"]))
check("เรียงจากค้างนานที่สุด",
      [x["days_overdue"] for x in ov_list["items"]]
      == sorted((x["days_overdue"] for x in ov_list["items"]), reverse=True))
check("แต่ละงวดบอกครบว่าใครขาย ของอะไร PO ไหน",
      all(x["vendor_name"] and x["part_num"] and x["po_num"] is not None
          for x in ov_list["items"]), ov_list["items"][0])

s, late_list = call("/deliveries?only_late=true&limit=20")
check("ดูเฉพาะงวดที่ส่งช้าได้",
      s == 200 and all(x["delivered"] and not x["on_time"] and x["days_late"] > 0
                       for x in late_list["items"]))

s, ontime_list = call("/deliveries?only_on_time=true&sort=earliest&limit=20")
check("ดูเฉพาะงวดที่ส่งตรงเวลาได้",
      s == 200 and ontime_list["total"] > 0
      and all(x["delivered"] and x["on_time"] for x in ontime_list["items"]),
      ontime_list.get("total"))
check("งวดตรงเวลาไม่มีวันช้าเป็นบวก",
      all(x["days_late"] is not None and x["days_late"] <= 0 for x in ontime_list["items"]))
check("เรียงจากส่งเร็วกว่ากำหนดมากที่สุด",
      [x["days_late"] for x in ontime_list["items"]]
      == sorted(x["days_late"] for x in ontime_list["items"]))

s, all_list = call("/deliveries?limit=20")
check("ดูทุกงวดรวมกันได้ ทั้งที่ตรงเวลาและช้า",
      s == 200 and all_list["total"] >= ontime_list["total"] + late_list["total"],
      (all_list.get("total"), ontime_list.get("total"), late_list.get("total")))

s, filtered = call("/deliveries?only_late=true&min_days_late=30&limit=20")
check("กรองเฉพาะที่ช้าเกินกี่วันได้",
      s == 200 and all(x["days_late"] >= 30 for x in filtered["items"]),
      [x["days_late"] for x in filtered["items"]][:5])

from urllib.parse import quote as _quote
vname = ov_list["items"][0]["vendor_name"].split()[0]
s, searched = call("/deliveries?only_overdue=true&q=" + _quote(vname))
check("ค้นด้วยชื่อผู้ขายได้",
      s == 200 and all(vname in x["vendor_name"] for x in searched["items"]), searched.get("total"))

s, by_v = call("/deliveries/by-vendor?only_overdue=true")
check("สรุปงานค้างส่งแยกรายผู้ขายได้",
      s == 200 and by_v["total_vendors"] > 0 and by_v["total_releases"] > 0, by_v.get("total_vendors"))
check("ยอดรวมรายผู้ขายตรงกับจำนวนงวดทั้งหมด",
      by_v["total_releases"] == ov_list["total"], (by_v["total_releases"], ov_list["total"]))
check("แต่ละผู้ขายมีตัวอย่างงวดจริงติดมาด้วย",
      all(len(v["items"]) > 0 and v["items"][0]["part_num"] for v in by_v["vendors"]))
check("ตัวอย่างของแต่ละรายเรียงจากค้างนานสุด",
      all([i["days_overdue"] for i in v["items"]]
          == sorted((i["days_overdue"] for i in v["items"]), reverse=True)
          for v in by_v["vendors"]))
check("รายผู้ขายพก OTD รวมมาด้วย เพื่อดูว่าค้างครั้งนี้ผิดปกติไหม",
      all("delivery" in v for v in by_v["vendors"]))
check("เรียงจากผู้ขายที่ค้างเยอะที่สุด",
      [v["releases"] for v in by_v["vendors"]]
      == sorted((v["releases"] for v in by_v["vendors"]), reverse=True))

s, by_v_ok = call("/deliveries/by-vendor?only_on_time=true&sort=days")
check("สรุปงวดที่ส่งตรงเวลาแยกรายผู้ขายได้",
      s == 200 and by_v_ok["total_releases"] == ontime_list["total"],
      (by_v_ok.get("total_releases"), ontime_list.get("total")))
check("มุมส่งตรงเวลาเรียงจากรายที่ส่งเร็วกว่ากำหนดมากสุด",
      [v["worst_days"] for v in by_v_ok["vendors"]]
      == sorted(v["worst_days"] for v in by_v_ok["vendors"]))
check("ตัวอย่างในมุมตรงเวลาเรียงจากเร็วสุดก่อน",
      all([i["days_late"] for i in v["items"]] == sorted(i["days_late"] for i in v["items"])
          for v in by_v_ok["vendors"]))

# ------------------------------------------------------- ประมาณราคา BOM
bom_text = "\t".join(["รายการ", "จำนวน", "หน่วย"]) + "\n"
bom_text += "{}\t2\tEA\n".format(det["description"][:40])
bom_text += "ของที่ไม่มีในระบบแน่ ๆ zxqwvv\t3\tEA\n"
s, pr = call("/boms/parse", "POST", {"text": bom_text})
check("อ่าน BOM ที่วางมาได้ แยกชื่อกับจำนวนถูก",
      s == 200 and pr["count"] == 2 and pr["lines"][0]["qty"] == 2
      and pr["lines"][1]["qty"] == 3, pr)
check("ไม่เอาแถวหัวตารางมาเป็นรายการ",
      all("รายการ" != l["name"] for l in pr["lines"]), pr["lines"])

# BOM จริงมีชื่อโครงการ/ผู้จัดทำอยู่เหนือหัวตาราง และมีหัวข้อหมวดคั่นกลาง
messy = "\n".join([
    "ใบรายการวัสดุ (BILL OF MATERIALS)",
    "โครงการ: ปรับปรุงระบบสื่อสาร",
    "",
    "\t".join(["ลำดับ", "รหัสสินค้า", "รายการ", "จำนวน", "หน่วย"]),
    "\t".join(["", "", "หมวดที่ 1 : งานระบบสื่อสาร", "", ""]),
    "\t".join(["1", "", "Ethernet switch industrial", "4", "EA"]),
    "\t".join(["2", "", "สายไฟเบอร์ออปติก", "1,200", "M"]),
])
s, mp = call("/boms/parse", "POST", {"text": messy})
names = [l["name"] for l in mp["lines"]]
check("ข้ามหัวเอกสารที่อยู่เหนือหัวตาราง",
      not any("BILL OF MATERIALS" in n or n.startswith("โครงการ") for n in names), names)
check("ข้ามหัวข้อหมวด ไม่นับเป็นของที่ต้องซื้อ",
      not any(n.startswith("หมวด") for n in names), names)
check("อ่านได้เฉพาะรายการจริง 2 บรรทัด", mp["count"] == 2, names)
check("จำนวนที่ใส่ลูกน้ำอ่านเป็นตัวเลขถูก",
      any(l["qty"] == 1200 for l in mp["lines"]), mp["lines"])

s, bom = call("/boms", "POST", {
    "title": "ทดสอบประมาณราคา", "contingency_percent": 10, "vat_percent": 7,
    "lines": pr["lines"]})
check("สร้างงานประมาณราคาได้ + ได้เลขที่", s == 201 and bom["bom_no"].startswith("BOM-"), bom)
bom_id = bom["id"]
l1 = bom["lines"][0]
l2 = bom["lines"][1]
check("จับคู่สินค้าที่มีอยู่จริงให้อัตโนมัติ", l1["matched"] and l1["unit_price"] is not None, l1)
check("ใช้ราคาซื้อล่าสุดเป็นฐาน พร้อมบอกวันที่",
      l1["price_source"] == "last_price" and l1["price_date"], l1)
check("คิดจำนวนเงินต่อบรรทัดถูก",
      abs(l1["amount"] - l1["unit_price"] * l1["qty"]) < 0.01, l1)
check("ของที่ไม่มีในระบบ ไม่จับคู่มั่ว ปล่อยว่างไว้",
      not l2["matched"] and l2["amount"] is None, l2)

t = bom["totals"]
check("ยอดรวมบอกด้วยว่าครอบคลุมกี่รายการ",
      t["line_count"] == 2 and t["priced_lines"] == 1 and t["unpriced_lines"] == 1
      and t["coverage_percent"] == 50.0, t)
check("ยอดรวมคิดเฉพาะรายการที่มีราคา", abs(t["subtotal"] - l1["amount"]) < 0.01, t)
check("บวกเผื่อสำรองและ VAT ถูกต้อง",
      abs(t["contingency_amount"] - t["subtotal"] * 0.10) < 0.01
      and abs(t["total"] - (t["before_vat"] + t["before_vat"] * 0.07)) < 0.01, t)

s, cand = call("/boms/{}/lines/1/candidates?limit=5".format(bom_id))
check("ขอรายการสินค้าใกล้เคียงของบรรทัดนั้นได้",
      s == 200 and len(cand["items"]) > 0
      and all("match_score" in i for i in cand["items"]), cand.get("query"))
check("ผู้สมัครเรียงจากตรงที่สุดก่อน",
      [i["match_score"] for i in cand["items"]]
      == sorted((i["match_score"] for i in cand["items"]), reverse=True))

other = next((i for i in cand["items"] if i["part_num"] != l1["part_num"]), None)
if other:
    s, v = call("/boms/{}/lines/1".format(bom_id), "PATCH", {"part_num": other["part_num"]})
    got = v["lines"][0]
    check("เลือกสินค้าใหม่ให้บรรทัดนั้นได้ (คลิกรายตัว)",
          s == 200 and got["part_num"] == other["part_num"]
          and got["match_source"] == "manual", got)

s, v = call("/boms/{}/lines/1".format(bom_id), "PATCH", {"part_num": "ไม่มีรหัสนี้จริง"})
check("ผูกกับรหัสที่ไม่มีอยู่ไม่ได้", s == 400, (s, v))

s, v = call("/boms/{}/lines/2".format(bom_id), "PATCH", {"manual_price": 1500})
line2 = v["lines"][1]
check("กรอกราคาเองให้ของที่ไม่มีในระบบได้",
      s == 200 and line2["unit_price"] == 1500 and line2["price_source"] == "manual"
      and line2["amount"] == 4500, line2)
check("กรอกราคาเองแล้วความครอบคลุมเป็น 100%", v["totals"]["coverage_percent"] == 100.0)

s, v = call("/boms/{}/lines/2".format(bom_id), "PATCH", {"qty": 10})
check("แก้จำนวนแล้วยอดคิดใหม่ทันที", v["lines"][1]["amount"] == 15000, v["lines"][1])

s, v = call("/boms/{}".format(bom_id), "PATCH", {"contingency_percent": 20})
check("ปรับ % เผื่อสำรองแล้วงบเปลี่ยนตาม",
      abs(v["totals"]["contingency_amount"] - v["totals"]["subtotal"] * 0.20) < 0.01, v["totals"])

s, v = call("/boms/{}/rematch".format(bom_id), "POST")
check("สั่งจับคู่ใหม่แล้วไม่ทับบรรทัดที่คนเลือกเอง",
      s == 200 and v["lines"][0]["match_source"] == "manual"
      and v["lines"][1]["unit_price"] == 1500, v["lines"])

s, made = call("/boms/{}/rfq".format(bom_id), "POST", {"vendor_keys": []})
check("ออกใบขอราคาจาก BOM ได้ นับเฉพาะบรรทัดที่จับคู่แล้ว",
      s == 201 and made["line_count"] == 1 and made["skipped_lines"] == 1, made)
check("ใบขอราคาที่ออกอ้างถึงงานประมาณราคานี้",
      "BOM-" in (made["rfq"].get("note") or ""), made["rfq"].get("note"))

s = status_of("/boms/{}/export".format(bom_id))
check("โหลดงบเป็นไฟล์ Excel ได้", s == 200, s)

s, lst = call("/boms?limit=5")
check("หน้ารายการเห็นงานที่ทำไว้ พร้อมความครอบคลุม",
      s == 200 and lst["total"] >= 1
      and lst["items"][0]["coverage_percent"] is not None, lst.get("total"))

s, empty = call("/boms", "POST", {"title": "ไม่มีบรรทัด", "lines": []})
check("สร้างงานโดยไม่มีรายการไม่ได้", s == 400, (s, empty))


# ------------------------------------------------------- ออก RFQ แยกรายตัวจาก BOM
s, bom2 = call("/boms", "POST", {
    "title": "ทดสอบออกใบแยกรายตัว", "contingency_percent": 0, "vat_percent": 7,
    "lines": [{"name": det["description"][:40], "qty": 3, "uom": "EA"},
              {"name": "ของที่ไม่มีในระบบ qqzzxx", "qty": 1, "uom": "EA"}]})
bid2 = bom2["id"]

s, plan = call("/boms/{}/rfq-plan".format(bid2))
check("ขอแผนออกใบแยกรายตัวได้", s == 200 and len(plan["items"]) >= 1, plan.get("items"))
check("รายการที่ยังไม่จับคู่ถูกแยกไว้ต่างหาก พร้อมบอกเหตุผล",
      len(plan["skipped"]) == 1 and plan["skipped"][0]["reason"], plan.get("skipped"))

first_item = plan["items"][0]
check("แต่ละรายการพกผู้ขายที่เคยขายรหัสนั้นมาด้วย",
      len(first_item["vendors"]) > 0
      and all(v["vendor_key"].startswith("epicor:") for v in first_item["vendors"]),
      first_item.get("vendor_count"))
check("ผู้ขายแต่ละรายมีทั้งราคาล่าสุดของเจ้านั้นและคะแนนความตรงเวลา",
      all("last_unit_cost" in v and "delivery" in v for v in first_item["vendors"]),
      list(first_item["vendors"][0].keys()))
sugg = [v for v in first_item["vendors"] if v["suggested"]]
check("ติ๊กไว้ให้ไม่เกิน 3 ราย และต้องเป็นรายที่มีราคาเท่านั้น",
      0 < len(sugg) <= 3 and all(v["last_unit_cost"] is not None for v in sugg),
      [(v["name"], v["last_unit_cost"]) for v in sugg])
check("รายที่ติ๊กไว้คือรายที่ราคาถูกที่สุด",
      [v["last_unit_cost"] for v in sugg]
      == sorted(v["last_unit_cost"] for v in first_item["vendors"]
                if v["last_unit_cost"] is not None)[:len(sugg)])

picked_keys = [v["vendor_key"] for v in sugg][:2]
s, made = call("/boms/{}/rfqs".format(bid2), "POST", {
    "group_by": "item",
    "items": [{"line_no": first_item["line_no"], "vendor_keys": picked_keys},
              {"line_no": 2, "vendor_keys": []}]})
check("ออกใบขอราคาแยกรายตัวได้", s == 201 and len(made["created"]) == 1, made)
check("รายการที่ออกใบไม่ได้ ถูกข้ามพร้อมบอกเหตุผลที่ตรงจริง",
      len(made["skipped"]) == 1 and "จับคู่" in made["skipped"][0]["reason"], made.get("skipped"))

new_rfq = made["created"][0]
s, rfq_doc = call("/rfqs/{}".format(new_rfq["rfq_id"]))
check("ใบที่ออกมีสินค้าแค่รายการเดียว (ไม่รวมทั้ง BOM)",
      s == 200 and len(rfq_doc["lines"]) == 1
      and rfq_doc["lines"][0]["part_num"] == first_item["part_num"], rfq_doc.get("lines"))
check("จำนวนในใบตรงกับที่ระบุใน BOM", rfq_doc["lines"][0]["qty"] == 3, rfq_doc["lines"][0])
s, invites = call("/rfqs/{}/invites".format(new_rfq["rfq_id"]))
check("เชิญเฉพาะผู้ขายที่เลือกไว้ ไม่ใช่ทุกราย",
      sorted(i["vendor_key"] for i in invites) == sorted(picked_keys),
      [i["vendor_key"] for i in invites])

s, after = call("/boms/{}".format(bid2))
line1 = [l for l in after["lines"] if l["line_no"] == first_item["line_no"]][0]
check("บรรทัดใน BOM จำได้ว่าออกใบไหนไปแล้ว",
      line1["rfq_no"] == new_rfq["rfq_no"] and line1["rfq_id"], line1.get("rfq_no"))
check("บรรทัดที่ยังไม่ได้ออกใบ ยังว่างอยู่",
      [l for l in after["lines"] if l["line_no"] == 2][0]["rfq_no"] == "")

s, none_ = call("/boms/{}/rfqs".format(bid2), "POST", {"items": []})
check("ไม่เลือกรายการเลย ออกใบไม่ได้", s == 400, (s, none_))
# จับคู่แล้วแต่ไม่ติ๊กผู้ขายสักราย = ใบที่ไม่มีใครตอบ ต้องกันไว้และบอกเหตุผลให้ตรง
s, blank = call("/boms/{}/rfqs".format(bid2), "POST",
                {"items": [{"line_no": first_item["line_no"], "vendor_keys": []}]})
check("จับคู่แล้วแต่ไม่เลือกผู้ขาย ก็ออกไม่ได้ พร้อมบอกว่าทำไม",
      s == 400 and "ผู้ขาย" in str(blank.get("detail", "")), (s, blank))
s, unmatched = call("/boms/{}/rfqs".format(bid2), "POST",
                    {"items": [{"line_no": 2, "vendor_keys": ["epicor:99999"]}]})
check("รายการที่ยังไม่จับคู่ ออกใบไม่ได้ แม้จะระบุผู้ขายมา",
      s == 400 and "จับคู่" in str(unmatched.get("detail", "")), (s, unmatched))

# ค้นหาผู้ขายเพิ่ม — ตามชื่อ และตามอุปกรณ์ที่ใกล้เคียง
s, byname = call("/boms/{}/lines/{}/vendor-search?by=name&q={}".format(
    bid2, first_item["line_no"], "moxa"))
check("ค้นผู้ขายเพิ่มตามชื่อได้", s == 200 and byname["by"] == "name", byname.get("total"))
s, noq = call("/boms/{}/lines/{}/vendor-search?by=name".format(bid2, first_item["line_no"]))
check("ค้นตามชื่อโดยไม่ใส่คำค้น ต้องบอกว่าต้องพิมพ์อะไรมา", noq and s == 400, (s, noq))

s, byitem = call("/boms/{}/lines/{}/vendor-search?by=item".format(bid2, first_item["line_no"]))
check("ค้นผู้ขายจากอุปกรณ์ที่ใกล้เคียงได้ โดยไม่ต้องพิมพ์คำค้น (ใช้ชื่อจาก BOM)",
      s == 200 and byitem["query"] == first_item["name"] and len(byitem["items"]) > 0,
      byitem.get("query"))
check("บอกด้วยว่าค้นจากสินค้าตัวไหน — ตรวจย้อนกลับได้",
      len(byitem["via_items"]) > 0
      and all(v.get("via_items") for v in byitem["items"]), byitem.get("via_items"))
check("ผู้ขายจากการค้นแบบนี้มีคะแนนความตรงเวลาติดมาด้วย",
      all("delivery" in v for v in byitem["items"]))
check("เรียงจากรายที่ขายของตรงกับที่หาที่สุดก่อน",
      [v["match_score"] for v in byitem["items"]]
      == sorted((v["match_score"] for v in byitem["items"]), reverse=True))

s, bad = call("/boms/{}/lines/9999/vendor-search?by=item".format(bid2))
check("ค้นผู้ขายของบรรทัดที่ไม่มีอยู่ คืน 404", s == 404, (s, bad))

# ---- ขอราคาเพิ่มจากหน้าวัสดุรายตัว (ออกใบเพิ่มทีหลัง ไม่ใช่แค่รอบแรก)
s, one = call("/boms/{}/rfq-plan?line_no={}".format(bid2, first_item["line_no"]))
check("ขอแผนเฉพาะบรรทัดเดียวได้ ไม่ต้องดึงทั้งโครงการ",
      s == 200 and len(one["items"]) == 1
      and one["items"][0]["line_no"] == first_item["line_no"], one.get("items"))
already = [v for v in one["items"][0]["vendors"] if v.get("invited")]
check("ผู้ขายที่เชิญไปแล้วถูกติดธงไว้ พร้อมเลขที่ใบ",
      sorted(v["vendor_key"] for v in already) == sorted(picked_keys)
      and all(v["invited_rfqs"] for v in already),
      [(v["name"], v.get("invited_rfqs")) for v in already])
check("เจ้าที่เชิญไปแล้วจะไม่ถูกติ๊กไว้ให้ซ้ำอีก",
      all(not v["suggested"] for v in already))

s, srch = call("/boms/{}/lines/{}/vendor-search?by=item".format(bid2, first_item["line_no"]))
hits = {v["vendor_key"]: v for v in srch["items"]}
check("ผลค้นหาผู้ขายก็ติดธง 'เชิญแล้ว' มาด้วย",
      all(hits[k]["invited"] for k in picked_keys if k in hits)
      and any(k in hits for k in picked_keys), list(hits)[:3])

# เชิญเจ้าใหม่ 1 ราย ระบบต้องออกใบเพิ่มให้ โดยไม่แตะใบเดิม
# รหัสนี้อาจมีผู้ขายในระบบไม่กี่ราย และถูกเชิญไปหมดแล้ว จึงเผื่อหยิบจากผลค้นหาด้วย
outsiders = [v["vendor_key"] for v in one["items"][0]["vendors"] if not v.get("invited")]
outsiders += [k for k, v in hits.items() if not v.get("invited") and k not in outsiders]
fresh = outsiders[:1]
check("มีผู้ขายที่ยังไม่ได้เชิญให้เลือกเพิ่ม", len(fresh) == 1, outsiders)
s, more = call("/boms/{}/rfqs".format(bid2), "POST", {
    "group_by": "vendor",
    "items": [{"line_no": first_item["line_no"], "vendor_keys": fresh}]})
check("ขอราคาเพิ่มจากเจ้าใหม่ได้ทีหลัง", s == 201 and len(more["created"]) == 1, more)
check("ใบใหม่เป็นคนละใบกับใบเดิม",
      more["created"][0]["rfq_no"] != new_rfq["rfq_no"], more["created"][0])

s, after2 = call("/boms/{}".format(bid2))
line_after = [l for l in after2["lines"] if l["line_no"] == first_item["line_no"]][0]
check("บรรทัดเดียวจำใบขอราคาได้ทุกใบ ไม่ใช่ทับใบเดิม",
      len(line_after["rfqs"]) == 2, line_after.get("rfqs"))

# เชิญเจ้าเดิมซ้ำ = ต้องถูกตัดออกให้ ไม่ใช่ส่งไปหาเขาสองรอบเงียบ ๆ
s, dup = call("/boms/{}/rfqs".format(bid2), "POST", {
    "group_by": "vendor",
    "items": [{"line_no": first_item["line_no"], "vendor_keys": picked_keys}]})
check("เชิญเจ้าที่เคยเชิญซ้ำ ระบบตัดให้และบอกว่าตัดใครออก",
      s == 400 and "เชิญ" in str(dup.get("detail", "")), (s, dup))

s, dup2 = call("/boms/{}/rfqs".format(bid2), "POST", {
    "group_by": "vendor", "allow_repeat": True,
    "items": [{"line_no": first_item["line_no"], "vendor_keys": picked_keys[:1]}]})
check("ถ้ายืนยันว่าตั้งใจถามซ้ำ (allow_repeat) ก็ออกใบให้",
      s == 201 and len(dup2["created"]) == 1, dup2)

# ผสมกัน: เจ้าเดิม 1 + เจ้าใหม่ 1 → ออกให้เฉพาะเจ้าใหม่ และรายงานว่าข้ามใคร
mix_new = [k for k in outsiders if k not in fresh][:1]
if mix_new:
    s, mix = call("/boms/{}/rfqs".format(bid2), "POST", {
        "group_by": "vendor",
        "items": [{"line_no": first_item["line_no"],
                   "vendor_keys": mix_new + picked_keys[:1]}]})
    check("เลือกปนกัน — ออกให้เฉพาะเจ้าใหม่ ส่วนเจ้าเดิมรายงานว่าข้าม",
          s == 201 and len(mix["created"]) == 1
          and mix["created"][0]["vendor_key"] == mix_new[0]
          and len(mix["repeated"]) == 1, mix)

# หาสินค้าสองรหัสที่ต่างกัน และมี "ผู้ขายร่วมกันอย่างน้อย 2 ราย"
# ต้องมีผู้ขายร่วม ไม่งั้นทดสอบการรวมใบตามผู้ขายไม่ได้เลย
pairs = []
s, pool = call("/catalog/items?limit=40")
for cand in pool["items"][:14]:
    if cand["vendor_count"] < 2:
        continue
    s, full = call("/catalog/items/" + cand["part_num"])
    pairs.append((cand["part_num"], {v["vendor_key"] for v in full["vendors"]}))

two_parts, shared_vendors = [], []
for i in range(len(pairs)):
    for j in range(i + 1, len(pairs)):
        common = sorted(pairs[i][1] & pairs[j][1])
        if len(common) >= 2:
            two_parts = [pairs[i][0], pairs[j][0]]
            shared_vendors = common[:2]
            break
    if two_parts:
        break
check("มีสินค้า 2 รหัสที่ผู้ขายร่วมกันอย่างน้อย 2 ราย ไว้ทดสอบการรวมใบ",
      len(two_parts) == 2 and len(shared_vendors) == 2, (two_parts, shared_vendors))


def make_bom_with(title, qtys):
    """สร้าง BOM แล้วบังคับให้แต่ละบรรทัดผูกกับรหัสที่เลือกไว้ — ทดสอบจะได้ไม่ขึ้นกับการเดาของตัวจับคู่"""
    _, doc = call("/boms", "POST", {
        "title": title, "contingency_percent": 0, "vat_percent": 7,
        "lines": [{"name": "รายการทดสอบ {}".format(i + 1), "qty": q, "uom": "EA"}
                  for i, q in enumerate(qtys)]})
    for i, part_num in enumerate(two_parts):
        call("/boms/{}/lines/{}".format(doc["id"], i + 1), "PATCH", {"part_num": part_num})
    return doc["id"]


# ------------------------------------------------------- รวมใบตามผู้ขาย + สถานะงาน
bid3 = make_bom_with("ทดสอบรวมใบตามผู้ขาย", [2, 5])
s, plan3 = call("/boms/{}/rfq-plan".format(bid3))
shared = shared_vendors
# ผู้ขายชุดเดียวกันขายทั้งสองรายการ → ควรได้ใบเท่าจำนวนผู้ขาย ไม่ใช่เท่าจำนวนรายการ
items3 = [{"line_no": it["line_no"], "vendor_keys": shared} for it in plan3["items"]]

s, byv = call("/boms/{}/rfqs".format(bid3), "POST",
              {"items": items3, "group_by": "vendor"})
check("ผู้ขายรายเดียวกันขายหลายรายการ ได้ใบเดียว ไม่ใช่ใบละรายการ",
      s == 201 and len(byv["created"]) == len(shared), 
      [(c["vendor_name"], c["line_count"]) for c in byv.get("created", [])])
check("ใบของผู้ขายรายนั้นมีของครบทุกรายการที่เลือกเขาไว้",
      all(c["line_count"] == len(items3) for c in byv["created"]),
      [(c["vendor_name"], c["line_count"]) for c in byv["created"]])

s, rfq3 = call("/rfqs/{}".format(byv["created"][0]["rfq_id"]))
check("เปิดใบแล้วเห็นทุกรายการอยู่ในใบเดียวกัน", len(rfq3["lines"]) == len(items3), rfq3["lines"])
s, inv3 = call("/rfqs/{}/invites".format(byv["created"][0]["rfq_id"]))
check("ใบนั้นเชิญผู้ขายรายเดียว", len(inv3) == 1, inv3)

s, after3 = call("/boms/{}".format(bid3))
line = after3["lines"][0]
check("บรรทัดจำได้ว่าตัวเองอยู่ในใบของผู้ขายหลายเจ้า",
      len(line["rfqs"]) == len(shared), line.get("rfqs"))

# ---- สถานะเดินตามงานจริง
check("ออกใบแล้วยังไม่ส่ง = ขั้น 'ออกใบขอราคาแล้ว'",
      line["stage"] == "rfq_draft" and line["stage_label"], line.get("stage"))
rid3 = byv["created"][0]["rfq_id"]
call("/rfqs/{}/send".format(rid3), "POST", {"message": "รบกวนเสนอราคา"})
s, after3 = call("/boms/{}".format(bid3))
check("ส่งให้ผู้ขายแล้ว สถานะขยับเป็น 'ส่งให้ผู้ขายแล้ว'",
      after3["lines"][0]["stage"] == "rfq_sent", after3["lines"][0]["stage"])
check("ภาพรวมโครงการนับรายการที่รอผู้ขายตอบ",
      after3["progress"]["waiting_lines"] >= 1, after3["progress"])

s, inv3 = call("/rfqs/{}/invites".format(rid3))
tok3 = inv3[0]["token"]
call("/portal/{}/accept-terms".format(tok3), "POST", {"accepted": True})
call("/portal/{}/quote".format(tok3), "POST", {
    "lines": [{"part_num": l["part_num"], "unit_price": 111.0} for l in rfq3["lines"]],
    "currency": "THB", "vat_percent": 7})
s, after3 = call("/boms/{}".format(bid3))
check("ผู้ขายเสนอราคากลับมา สถานะเป็น 'ได้รับราคาแล้ว'",
      after3["lines"][0]["stage"] == "quoted"
      and after3["lines"][0]["quote_count"] >= 1, after3["lines"][0].get("stage"))

s, cmp3 = call("/rfqs/{}/comparison".format(rid3))
call("/rfqs/{}/award".format(rid3), "POST",
     {"vendor_key": cmp3["best_total_vendor_key"], "reason": "ราคาต่ำสุด"})
s, after3 = call("/boms/{}".format(bid3))
done_line = after3["lines"][0]
check("อนุมัติราคาแล้ว สถานะเป็น 'อนุมัติราคาแล้ว' พร้อมชื่อผู้ชนะ",
      done_line["stage"] == "awarded" and done_line["award"]["vendor_name"],
      done_line.get("award"))
check("บอกด้วยว่าราคาที่อนุมัติต่างจากงบที่ตั้งไว้กี่ %",
      done_line["award"]["vs_estimate_pct"] is not None, done_line["award"])
check("ภาพรวมโครงการสรุปราคาที่อนุมัติแล้วเทียบงบ",
      after3["progress"]["awarded_lines"] >= 1
      and after3["progress"]["approved_amount"] > 0
      and after3["progress"]["approved_vs_estimate_pct"] is not None,
      after3["progress"])
check("ทุกขั้นของกระบวนการมีชื่อกำกับครบ",
      len(after3["progress"]["stages"]) == 6
      and all(x["label"] for x in after3["progress"]["stages"]))

s, lst3 = call("/boms?limit=5")
mine = [b for b in lst3["items"] if b["id"] == bid3][0]
check("หน้ารายการเห็นความคืบหน้าโดยไม่ต้องเปิดเข้าไป",
      mine["progress"].get("asked_lines", 0) >= 1, mine.get("progress"))

# ------------------------------------------------------- เทียบราคารายสินค้าทั้งโครงการ
bid4 = make_bom_with("ทดสอบเทียบราคารายสินค้า", [2, 4])
s, plan4 = call("/boms/{}/rfq-plan".format(bid4))
two = shared_vendors
s, made4 = call("/boms/{}/rfqs".format(bid4), "POST", {
    "items": [{"line_no": it["line_no"], "vendor_keys": two} for it in plan4["items"]],
    "group_by": "vendor", "send": True})

# ให้ผู้ขายทั้งสองเสนอราคาคนละราคา เพื่อดูว่าไฮไลต์ถูกสุดถูกแถว
prices = {}
for n, c in enumerate(made4["created"]):
    s, inv4 = call("/rfqs/{}/invites".format(c["rfq_id"]))
    s, rfq4 = call("/rfqs/{}".format(c["rfq_id"]))
    t = inv4[0]["token"]
    call("/portal/{}/accept-terms".format(t), "POST", {"accepted": True})
    lines4 = []
    for i, l in enumerate(rfq4["lines"]):
        unit = 1000 * (i + 1) * (n + 1)
        prices[(c["vendor_key"], l["part_num"], i)] = unit
        lines4.append({"part_num": l["part_num"], "unit_price": unit, "lead_time_days": 7 + n})
    call("/portal/{}/quote".format(t), "POST",
         {"lines": lines4, "currency": "THB", "vat_percent": 7})

s, cmp4 = call("/boms/{}/comparison".format(bid4))
check("เทียบราคาเป็นแถวละสินค้า ไม่ใช่แถวละใบ",
      s == 200 and len(cmp4["rows"]) == 2
      and all(r["part_num"] for r in cmp4["rows"]), len(cmp4.get("rows", [])))
check("คอลัมน์เป็นผู้ขาย รวมจากทุกใบของโครงการ",
      len(cmp4["vendors"]) == 2 and cmp4["summary"]["quoted_vendors"] == 2,
      [v["vendor_name"] for v in cmp4["vendors"]])
# ถ้าช่องเรียงไม่ตรงกับหัวคอลัมน์ ราคาของเจ้าหนึ่งจะไปโผล่ใต้ชื่ออีกเจ้า — ผิดแบบมองไม่เห็น
check("ช่องราคาเรียงตรงกับหัวคอลัมน์ทุกแถว",
      all([c["vendor_key"] for c in r["cells"]] == [v["vendor_key"] for v in cmp4["vendors"]]
          for r in cmp4["rows"]),
      [[c["vendor_key"] for c in r["cells"]] for r in cmp4["rows"]])
check("ไฮไลต์ราคาต่ำสุดของแต่ละแถวถูกตัว",
      all(next(c for c in r["cells"] if c["is_lowest"])["unit_price"]
          == min(c["unit_price"] for c in r["cells"] if c["unit_price"] is not None)
          for r in cmp4["rows"]))
check("แต่ละแถวบอกว่าราคาที่ดีที่สุดต่างจากงบกี่ %",
      all(r["best_vs_estimate_pct"] is not None for r in cmp4["rows"]),
      [r.get("best_vs_estimate_pct") for r in cmp4["rows"]])
check("ยอดรวม 'เลือกถูกสุดรายชิ้น' คิดจากราคาต่ำสุดของแต่ละแถวจริง",
      abs(cmp4["summary"]["best_total"]
          - sum(r["best_unit_price"] * r["qty"] for r in cmp4["rows"])) < 0.01,
      cmp4["summary"])
check("ช่องว่างแยกได้ว่าไม่ได้เชิญ / ยังไม่ตอบ / ไม่เสนอรายการนี้",
      all(set(("invited", "answered", "no_quote")) <= set(c) for r in cmp4["rows"] for c in r["cells"]))

# ---- อนุมัติรายสินค้า: เลือกเจ้าที่ถูกสุดของแต่ละแถว
awards4 = [{"line_no": r["line_no"],
            "vendor_key": next(c["vendor_key"] for c in r["cells"] if c["is_lowest"])}
           for r in cmp4["rows"]]
s, res4 = call("/boms/{}/award".format(bid4), "POST",
               {"awards": awards4, "reason": "ราคาต่ำสุดรายชิ้น"})
check("อนุมัติผู้ชนะรายสินค้าจากหน้าเทียบราคาได้", s == 200 and res4["awarded"], res4)
won = {r["line_no"]: r for r in res4["bom"]["lines"] if r.get("award")}
check("ผู้ชนะที่บันทึกคือเจ้าที่เลือกไว้จริง (ไม่ใช่เจ้าอื่นในใบเดียวกัน)",
      all(won[a["line_no"]]["award"]["vendor_key"] == a["vendor_key"] for a in awards4),
      [(a["vendor_key"], won[a["line_no"]]["award"]["vendor_key"]) for a in awards4])
check("ราคาที่บันทึกคือราคาที่เจ้านั้นเสนอมาจริง",
      all(won[a["line_no"]]["award"]["unit_price"]
          == next(c["unit_price"] for c in
                  next(r for r in cmp4["rows"] if r["line_no"] == a["line_no"])["cells"]
                  if c["vendor_key"] == a["vendor_key"])
          for a in awards4))
check("อนุมัติแล้วสถานะรายการขยับเป็น 'อนุมัติราคาแล้ว' ครบทุกแถว",
      all(l["stage"] == "awarded" for l in res4["bom"]["lines"] if l["line_no"] in won))

s, cmp5 = call("/boms/{}/comparison".format(bid4))
check("กลับมาดูตารางเทียบราคา เห็นว่าแถวไหนอนุมัติไปแล้ว",
      all(r["award"] for r in cmp5["rows"]))

s, none4 = call("/boms/{}/award".format(bid4), "POST", {"awards": []})
check("ไม่เลือกผู้ชนะเลย อนุมัติไม่ได้", s == 400, (s, none4))
s, bad4 = call("/boms/{}/award".format(bid4), "POST",
               {"awards": [{"line_no": 1, "vendor_key": "epicor:00000"}]})
check("เลือกผู้ขายที่ไม่ได้อยู่ในใบของรายการนั้น อนุมัติไม่ได้ พร้อมบอกเหตุผล",
      s == 400 and "ผู้ขาย" in str(bad4.get("detail", "")), (s, bad4))

print("\n{} passed, {} failed".format(ok, fail))
sys.exit(1 if fail else 0)
