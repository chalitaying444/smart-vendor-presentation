"""ตรวจสิทธิ์การเห็นโครงการ — ส่วนที่ผิดแล้วเสียหายที่สุดของระบบนี้

ข้อมูลที่รั่วออกไปแล้วเรียกคืนไม่ได้ และการรั่วแบบนี้ไม่มีอาการให้เห็น
(ทุกอย่างดูทำงานปกติ แค่คนผิดคนได้เห็นราคาของโครงการที่ไม่ใช่ของตัวเอง)
จึงตรวจทั้งสองด้านเสมอ: คนที่ควรเห็นต้องเห็นจริง และคนที่ไม่ควรเห็นต้องถูกกันจริง
ทั้งในหน้ารายการ (ไม่โผล่) และตอนยิงตรงเข้า id (ถูกปฏิเสธ)
"""
import json
import sys
from urllib.parse import quote
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _env import BASE, token                  # noqa: E402

ADMIN = token()
ok = fail = 0


def call(path, method="GET", body=None, token=ADMIN):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
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
        print("FAIL", label, str(extra)[:220])


# ---------------------------------------------------------------- เตรียมผู้ใช้
def create(email, role, departments):
    status, res = call("/users", "POST", {
        "email": email, "display_name": email.split("@")[0],
        "role": role, "departments": departments, "is_active": True,
    })
    if status == 409:
        _, listed = call("/users?q=" + email)
        uid = listed["items"][0]["id"]
        call("/users/{}".format(uid), "PATCH",
                   {"role": role, "departments": departments, "is_active": True})
    s, tok = call("/auth/token?email={}".format(email), "POST")
    assert s == 200, (email, tok)
    return tok["access_token"]


BUY = "ฝ่ายจัดซื้อ"
PROJ = "ฝ่ายโครงการ"
TITLES = ("โครงการของฝ่ายจัดซื้อ", "โครงการของฝ่ายโครงการ")

# ล้างของค้างจากรอบก่อนที่ล้มกลางทางก่อนเริ่ม — ชื่อโครงการซ้ำจะทำให้เทสต์
# "ต้องไม่เห็นโครงการนี้" ไปเจอของรอบก่อนแล้วฟ้องผิด ๆ
for _title in TITLES:
    for _trash in ("", "&trash=true"):
        _s, _old = call("/boms?q={}&limit=100{}".format(quote(_title), _trash))
        for _row in (_old or {}).get("items", []):
            call("/boms/{}".format(_row["id"]), "DELETE")
            call("/boms/{}/purge".format(_row["id"]), "DELETE")

a1 = create("a1.access@precise.co.th", "staff", [BUY])
a2 = create("a2.access@precise.co.th", "staff", [BUY])
b1 = create("b1.access@precise.co.th", "staff", [PROJ])
c1 = create("c1.access@precise.co.th", "staff", [])
both = create("both.access@precise.co.th", "staff", [BUY, PROJ])

s, me = call("/users?q=a1.access", token=ADMIN)
check("admin ตั้งหน่วยงานให้ผู้ใช้ได้ และสังกัดได้หลายหน่วยงาน",
      me["items"][0]["departments"] == [BUY], me["items"][0].get("departments"))
s, both_row = call("/users?q=both.access", token=ADMIN)
check("คนเดียวอยู่ได้หลายหน่วยงาน",
      both_row["items"][0]["departments"] == [BUY, PROJ], both_row["items"][0].get("departments"))

# ---------------------------------------------------------------- สร้างโครงการ
s, items = call("/catalog/items?limit=2")
part = items["items"][0]["part_num"]

s, p1 = call("/boms", "POST", {
    "title": "โครงการของฝ่ายจัดซื้อ", "contingency_percent": 0, "vat_percent": 7,
    "lines": [{"name": items["items"][0]["description"][:40], "qty": 2, "uom": "EA"}],
}, token=a1)
check("สร้างโครงการได้ และหน่วยงานตั้งต้นมาจากหน่วยงานของคนสร้างเอง",
      s == 201 and p1["department"] == BUY, (s, p1.get("department")))
check("บันทึกเจ้าของโครงการไว้", p1["owner"] == "a1.access@precise.co.th", p1.get("owner"))
pid = p1["id"]

s, p2 = call("/boms", "POST", {
    "title": "โครงการของฝ่ายโครงการ", "contingency_percent": 0, "vat_percent": 7,
    "lines": [{"name": items["items"][1]["description"][:40], "qty": 1, "uom": "EA"}],
}, token=b1)
pid2 = p2["id"]


def titles(token, params=""):
    s_, res = call("/boms" + params, token=token)
    return [i["title"] for i in res["items"]]


# ---------------------------------------------------------------- ใครเห็นอะไร
check("คนในหน่วยงานเดียวกันเห็นโครงการของกันและกัน",
      "โครงการของฝ่ายจัดซื้อ" in titles(a2), titles(a2))
check("คนหน่วยงานอื่นไม่เห็นโครงการนี้ในรายการ",
      "โครงการของฝ่ายจัดซื้อ" not in titles(b1), titles(b1))
check("คนที่ยังไม่สังกัดหน่วยงานไหน ไม่เห็นของใครเลย",
      titles(c1) == [], titles(c1))
check("คนที่สังกัดสองหน่วยงาน เห็นทั้งสองฝั่ง",
      {"โครงการของฝ่ายจัดซื้อ", "โครงการของฝ่ายโครงการ"} <= set(titles(both)), titles(both))
check("admin เห็นทุกโครงการ",
      {"โครงการของฝ่ายจัดซื้อ", "โครงการของฝ่ายโครงการ"} <= set(titles(ADMIN)), None)

# ยิงตรงเข้า id — หน้ารายการซ่อนอย่างเดียวไม่พอ
s, blocked = call("/boms/{}".format(pid), token=b1)
check("ยิงตรงเข้า id ของโครงการหน่วยงานอื่น ถูกปฏิเสธ", s == 403, (s, blocked))
check("ข้อความบอกเหตุผลและทางออก ไม่ใช่แค่ 'ไม่มีสิทธิ์'",
      "หน่วยงาน" in str(blocked.get("detail", "")) and "เพิ่มคุณเข้าโครงการ" in str(blocked.get("detail", "")),
      blocked)

# ทุกเส้นทางที่แตะโครงการต้องถูกกัน ไม่ใช่แค่เส้นทางหลัก
for path, method, body in [
    ("/boms/{}/export".format(pid), "GET", None),
    ("/boms/{}/comparison".format(pid), "GET", None),
    ("/boms/{}/rfq-plan".format(pid), "GET", None),
    ("/boms/{}/lines/1/candidates".format(pid), "GET", None),
    ("/boms/{}/lines/1".format(pid), "PATCH", {"qty": 99}),
    ("/boms/{}/rematch".format(pid), "POST", None),
    ("/boms/{}".format(pid), "PATCH", {"title": "แอบเปลี่ยนชื่อ"}),
    ("/boms/{}".format(pid), "DELETE", None),
]:
    s, res = call(path, method, body, token=b1)
    check("กันการเข้าถึง {} {}".format(method, path.replace(pid, "<id>")), s == 403, (s, res))

# ---------------------------------------------------------------- assign ข้ามหน่วยงาน
s, res = call("/boms/{}/assignees".format(pid), "POST", {"add": ["b1.access@precise.co.th"]}, token=b1)
check("คนที่ไม่ใช่เจ้าของ assign ตัวเองเข้าโครงการไม่ได้", s == 403, (s, res))

s, res = call("/boms/{}/assignees".format(pid), "POST", {"add": ["b1.access@precise.co.th"]}, token=a1)
check("เจ้าของโครงการเพิ่มคนนอกหน่วยงานเข้ามาได้", s == 200, (s, res))
check("โครงการนี้เห็นได้แล้วสำหรับคนที่ถูกเพิ่ม",
      "โครงการของฝ่ายจัดซื้อ" in titles(b1), titles(b1))
s, opened = call("/boms/{}".format(pid), token=b1)
check("เปิดโครงการได้จริงหลังถูกเพิ่ม", s == 200 and opened["id"] == pid, s)

s, res = call("/boms/{}/assignees".format(pid), "POST",
              {"add": ["ไม่มีคนนี้@precise.co.th"]}, token=a1)
check("เพิ่มอีเมลที่ไม่มีบัญชี ระบบบอกว่าไม่พบ ไม่ใช่เงียบ ๆ แล้วนึกว่าสำเร็จ",
      res.get("unknown"), res)

s, res = call("/boms/{}/assignees".format(pid), "POST",
              {"remove": ["b1.access@precise.co.th"]}, token=a1)
check("ถอดคนออกจากโครงการได้", s == 200 and not res["assignees"], res)
check("ถอดออกแล้วมองไม่เห็นทันที",
      "โครงการของฝ่ายจัดซื้อ" not in titles(b1), titles(b1))

# ---------------------------------------------------------------- ย้ายหน่วยงาน
s, moved = call("/boms/{}".format(pid), "PATCH", {"department": PROJ}, token=a1)
check("เจ้าของย้ายโครงการไปหน่วยงานอื่นได้", s == 200 and moved["department"] == PROJ, moved.get("department"))
check("ย้ายแล้วหน่วยงานใหม่เห็นทันที", "โครงการของฝ่ายจัดซื้อ" in titles(b1), titles(b1))
check("ย้ายแล้วหน่วยงานเดิมไม่เห็นแล้ว", "โครงการของฝ่ายจัดซื้อ" not in titles(a2), titles(a2))
call("/boms/{}".format(pid), "PATCH", {"department": BUY}, token=a1)

# ---------------------------------------------------------------- ผู้ขาย/สินค้า เห็นได้ทุกคน
for label, path in [("ผู้ขาย", "/vendors?limit=5"), ("สินค้า", "/catalog/items?limit=5"),
                    ("ภาพรวม", "/catalog/overview"), ("การส่งของ", "/deliveries?limit=5")]:
    s, res = call(path, token=c1)
    got = res.get("items") if isinstance(res, dict) else None
    check("{} — ทุกคนยังเห็นได้ทั้งหมด (ไม่ถูกจำกัดตามหน่วยงาน)".format(label), s == 200, (s, path))

s, tx = call("/catalog/items/{}/transactions?limit=5".format(part), token=c1)
check("รายการซื้อขายย้อนหลังก็ยังเห็นได้ทั้งหมด", s == 200, s)

# ---------------------------------------------------------------- ใบขอราคาที่ออกจากโครงการ
s, det = call("/catalog/items/" + part, token=a1)
vendor_keys = [v["vendor_key"] for v in det["vendors"][:2]]
s, patched = call("/boms/{}/lines/1".format(pid), "PATCH", {"part_num": part}, token=a1)
s, made = call("/boms/{}/rfqs".format(pid), "POST", {
    "group_by": "vendor", "items": [{"line_no": 1, "vendor_keys": vendor_keys}]}, token=a1)
check("ออกใบขอราคาจากโครงการได้", s == 201 and made["created"], (s, made))
rfq_id = made["created"][0]["rfq_id"]
rfq_no = made["created"][0]["rfq_no"]


def rfq_nos(token):
    s_, res = call("/rfqs?limit=100", token=token)
    return [r["rfq_no"] for r in res["items"]]


check("คนในหน่วยงานเดียวกันเห็นใบขอราคาของโครงการ", rfq_no in rfq_nos(a2), rfq_no)
check("คนหน่วยงานอื่นไม่เห็นใบขอราคาที่ออกจากโครงการนั้น",
      rfq_no not in rfq_nos(b1),
      "ชื่อโครงการและราคารั่วผ่านหน้าใบขอราคา")
s, blocked_rfq = call("/rfqs/{}".format(rfq_id), token=b1)
check("ยิงตรงเข้าใบขอราคาของโครงการที่ไม่มีสิทธิ์ ก็ถูกปฏิเสธ", s == 403, (s, blocked_rfq))

# ใบที่ไม่ได้ออกจากโครงการ (ขอราคาจากหน้าสินค้าตรง ๆ) ต้องยังเห็นได้ทุกคนเหมือนเดิม
s, plain = call("/rfqs", "POST", {
    "title": "ขอราคาทั่วไปไม่ผูกโครงการ", "currency": "THB",
    "lines": [{"part_num": part, "qty": 1}], "vendor_keys": vendor_keys[:1]}, token=ADMIN)
check("ใบขอราคาที่ไม่ได้ออกจากโครงการ ทุกคนยังเห็นได้",
      plain["rfq_no"] in rfq_nos(b1), plain["rfq_no"])

# ---------------------------------------------------------------- ยกเลิกใบขอราคาใบเดียว
# (คนละเรื่องกับการลบโครงการ — บางทีออกใบผิด อยากยกเลิกแค่ใบนั้น)
s, solo = call("/boms/{}/rfqs".format(pid), "POST", {
    "group_by": "vendor", "allow_repeat": True,
    "items": [{"line_no": 1, "vendor_keys": vendor_keys[:1]}]}, token=a1)
check("ออกใบที่สองของรายการเดิมได้ (ยืนยันขอซ้ำ)", s == 201 and solo.get("created"), (s, solo))
solo_id = solo["created"][0]["rfq_id"]
solo_no = solo["created"][0]["rfq_no"]
call("/rfqs/{}/send".format(solo_id), "POST", {"message": "ขอราคา"}, token=a1)
s, solo_inv = call("/rfqs/{}/invites".format(solo_id))
solo_token = solo_inv[0]["token"]

s, res = call("/rfqs/{}".format(solo_id), "DELETE", token=b1)
check("คนที่ไม่มีสิทธิ์ในโครงการ ยกเลิกใบขอราคาของโครงการนั้นไม่ได้", s == 403, (s, res))
s, res = call("/rfqs/{}".format(solo_id), "DELETE", token=a2)
check("คนในหน่วยงานเดียวกันแต่ไม่ใช่เจ้าของโครงการ ก็ยกเลิกใบไม่ได้",
      s == 403 and "เจ้าของโครงการ" in str(res.get("detail", "")), (s, res))

s, res = call("/rfqs/{}".format(solo_id), "DELETE", token=a1)
check("เจ้าของโครงการยกเลิกใบขอราคาใบเดียวได้", s == 200, (s, res))
check("บอกจำนวนลิงก์ของผู้ขายที่ถูกตัด",
      res.get("links_revoked", 0) >= 1 and "ใช้ไม่ได้อีก" in res.get("message", ""), res)
check("ใบที่ยกเลิกหายจากรายการปกติ", solo_no not in rfq_nos(a1), rfq_nos(a1))
s, in_trash = call("/rfqs?trash=true&limit=100", token=a1)
check("แต่ยังอยู่ในโหมด 'ยกเลิกแล้ว' ให้กู้คืนได้",
      solo_no in [r["rfq_no"] for r in in_trash["items"]], [r["rfq_no"] for r in in_trash["items"]])

s, vendor_view = call("/portal/{}".format(solo_token), token=ADMIN)
check("ลิงก์ที่ออกไปแล้วถูกเพิกถอน — ผู้ขายเห็นว่าใบนี้ถูกยกเลิก",
      s == 200 and vendor_view.get("cancelled") is True, (s, vendor_view))
s, blocked = call("/portal/{}/quote".format(solo_token), "POST",
                  {"lines": [{"part_num": part, "unit_price": 5}], "currency": "THB"})
check("ผู้ขายส่งราคาเข้าใบที่ยกเลิกไม่ได้", s == 410, (s, blocked))

s, res = call("/rfqs/{}/restore".format(solo_id), "POST", token=a1)
check("กู้ใบที่ยกเลิกกลับมาได้ และลิงก์ใช้ได้อีกครั้ง",
      s == 200 and res.get("status") == "sent", (s, res))
s, vendor_back = call("/portal/{}".format(solo_token), token=ADMIN)
check("ผู้ขายเปิดลิงก์เดิมได้ตามปกติหลังกู้ใบ",
      s == 200 and not vendor_back.get("cancelled"), (s, vendor_back))

# ยกเลิกใบเดี่ยวไว้ก่อน แล้วลบโครงการ → กู้โครงการต้องไม่ลากใบที่คนตั้งใจยกเลิกกลับมา
call("/rfqs/{}".format(solo_id), "DELETE", token=a1)
call("/boms/{}".format(pid), "DELETE", token=a1)
s, res = call("/rfqs/{}/restore".format(solo_id), "POST", token=a1)
check("โครงการยังอยู่ในถังขยะ กู้ใบเดี่ยวไม่ได้ และบอกให้กู้โครงการก่อน",
      s == 400 and "กู้โครงการก่อน" in str(res.get("detail", "")), (s, res))
call("/boms/{}/restore".format(pid), "POST", token=a1)
check("กู้โครงการแล้ว ใบที่คนตั้งใจยกเลิกไว้ต้องไม่กลับมาเอง",
      solo_no not in rfq_nos(a1), rfq_nos(a1))
s, res = call("/rfqs/{}/restore".format(solo_id), "POST", token=a1)
check("แต่กู้ใบนั้นเองทีหลังได้", s == 200 and solo_no in rfq_nos(a1), (s, res))

# ---------------------------------------------------------------- ยกเลิกหลายใบพร้อมกัน
# ออกอีกสองใบไว้ทดสอบการติ๊กเลือกหลายใบ
bulk_ids = []
bulk_nos = []
bulk_tokens = []
for vk in vendor_keys[:2]:
    s, made_more = call("/boms/{}/rfqs".format(pid), "POST", {
        "group_by": "vendor", "allow_repeat": True,
        "items": [{"line_no": 1, "vendor_keys": [vk]}]}, token=a1)
    rid = made_more["created"][0]["rfq_id"]
    bulk_ids.append(rid)
    bulk_nos.append(made_more["created"][0]["rfq_no"])
    call("/rfqs/{}/send".format(rid), "POST", {"message": "ขอราคา"}, token=a1)
    s, inv_more = call("/rfqs/{}/invites".format(rid))
    bulk_tokens.append(inv_more[0]["token"])
check("เตรียมใบไว้ทดสอบยกเลิกหลายใบ", len(bulk_ids) == 2, bulk_nos)

s, res = call("/rfqs/bulk-cancel", "POST", {"rfq_ids": bulk_ids}, token=a1)
check("ยกเลิกหลายใบในครั้งเดียวได้", s == 200 and len(res["cancelled"]) == 2, (s, res))
check("บอกจำนวนลิงก์ที่ถูกตัดรวมทุกใบ", res.get("links_revoked", 0) >= 2, res)
check("ทุกใบที่เลือกหายจากรายการปกติ",
      all(no not in rfq_nos(a1) for no in bulk_nos), rfq_nos(a1))
for tok_ in bulk_tokens:
    s, v = call("/portal/{}".format(tok_), token=ADMIN)
    check("ลิงก์ของผู้ขายถูกเพิกถอนทุกใบที่เลือก", v.get("cancelled") is True, (s, v))

# เลือกปนกัน: ใบที่ยกเลิกแล้ว + ใบที่ไม่มีสิทธิ์ ต้องรายงานว่าข้ามใบไหนเพราะอะไร
s, res = call("/rfqs/bulk-cancel", "POST", {"rfq_ids": bulk_ids}, token=a1)
check("ยกเลิกซ้ำใบที่ยกเลิกแล้วทั้งชุด ระบบบอกว่าทำไม่ได้",
      s == 400 and "ยกเลิกไม่ได้สักใบ" in str(res.get("detail", "")), (s, res))

s, res = call("/rfqs/bulk-restore", "POST", {"rfq_ids": bulk_ids}, token=a1)
check("กู้คืนหลายใบในครั้งเดียวได้", s == 200 and len(res["restored"]) == 2, (s, res))
check("กู้แล้วกลับมาอยู่ในรายการทุกใบ",
      all(no in rfq_nos(a1) for no in bulk_nos), rfq_nos(a1))
s, v = call("/portal/{}".format(bulk_tokens[0]), token=ADMIN)
check("ลิงก์ของผู้ขายใช้ได้อีกครั้งหลังกู้หลายใบ", not v.get("cancelled"), v)

# เลือกใบที่ไม่มีสิทธิ์ปนมา — ใบที่ทำได้ต้องทำ ใบที่ทำไม่ได้ต้องถูกรายงาน
s, other = call("/rfqs", "POST", {
    "title": "ใบของ b1 ไม่ผูกโครงการ", "currency": "THB",
    "lines": [{"part_num": part, "qty": 1}], "vendor_keys": vendor_keys[:1]}, token=b1)
s, res = call("/rfqs/bulk-cancel", "POST",
              {"rfq_ids": [bulk_ids[0], other["id"]]}, token=a1)
check("เลือกปนใบที่ไม่มีสิทธิ์ — ยกเลิกเฉพาะใบที่ทำได้",
      s == 200 and len(res["cancelled"]) == 1 and len(res["skipped"]) == 1, (s, res))
check("บอกเหตุผลที่ข้ามใบนั้นด้วย",
      res["skipped"][0]["reason"], res["skipped"])
call("/rfqs/{}".format(other["id"]), "DELETE", token=b1)
call("/rfqs/bulk-cancel", "POST", {"rfq_ids": [bulk_ids[1]]}, token=a1)

# ---------------------------------------------------------------- ลบ = ถังขยะ
s, res = call("/boms/{}".format(pid), "DELETE", token=a2)
check("คนในหน่วยงานเดียวกันแต่ไม่ใช่เจ้าของ ลบโครงการไม่ได้", s == 403, (s, res))

# ส่งใบออกให้ผู้ขายก่อน จะได้ทดสอบสภาพเดียวกับของจริง (ผู้ขายถือลิงก์อยู่ในมือแล้ว)
s, sent_res = call("/rfqs/{}/send".format(rfq_id), "POST", {"message": "รบกวนเสนอราคา"}, token=a1)
check("ส่งใบขอราคาของโครงการออกไปให้ผู้ขายได้", s == 200 and sent_res.get("sent"), (s, sent_res))

# ก่อนลบ: ผู้ขายเปิดลิงก์ได้ปกติ
s, invites = call("/rfqs/{}/invites".format(rfq_id))
vendor_token = invites[0]["token"]
s, before = call("/portal/{}".format(vendor_token), token=ADMIN)
check("ก่อนลบโครงการ ผู้ขายเปิดลิงก์เสนอราคาได้ปกติ",
      s == 200 and not before.get("cancelled"), (s, before))

s, res = call("/boms/{}".format(pid), "DELETE", token=a1)
check("เจ้าของลบโครงการได้ และบอกว่าไปอยู่ถังขยะ",
      s == 200 and "ถังขยะ" in res.get("message", ""), (s, res))
check("ลบโครงการแล้วใบขอราคาที่ออกจากโครงการถูกยกเลิกไปด้วย",
      res.get("rfqs_cancelled", 0) >= 1 and "ยกเลิกใบขอราคา" in res.get("message", ""), res)
check("ใบที่ถูกยกเลิกหายจากรายการใบขอราคา", rfq_no not in rfq_nos(a1), rfq_nos(a1))
check("ใบที่ถูกยกเลิกหายจากรายการของคนในหน่วยงานด้วย", rfq_no not in rfq_nos(a2), rfq_nos(a2))
s, gone = call("/rfqs/{}".format(rfq_id), token=a1)
check("เปิดใบที่ถูกยกเลิก บอกว่ายกเลิกพร้อมโครงการ ไม่ใช่แค่ 'ไม่พบ'",
      s == 404 and "ยกเลิกพร้อมโครงการ" in str(gone.get("detail", "")), (s, gone))

# ผู้ขายที่ถือลิงก์อยู่ต้องเห็นว่ายกเลิก และส่งราคาเข้ามาไม่ได้อีก
s, cancelled_view = call("/portal/{}".format(vendor_token), token=ADMIN)
check("ผู้ขายเปิดลิงก์เดิมแล้วเห็นว่าใบนี้ถูกยกเลิก",
      s == 200 and cancelled_view.get("cancelled") is True, (s, cancelled_view))
check("หน้ายกเลิกไม่ส่งรายการสินค้าออกไปอีก",
      "lines" not in cancelled_view and "title" not in cancelled_view, list(cancelled_view.keys()))
s, blocked_quote = call("/portal/{}/quote".format(vendor_token), "POST",
                        {"lines": [{"part_num": part, "unit_price": 1}], "currency": "THB"})
check("ผู้ขายส่งราคาเข้าใบที่ยกเลิกแล้วไม่ได้ (กันฝั่งเซิร์ฟเวอร์)",
      blocked_quote and "ยกเลิก" in str(blocked_quote.get("detail", "")), (s, blocked_quote))
s, blocked_doc = call("/portal/{}/document".format(vendor_token))
check("โหลดไฟล์ใบขอราคาที่ยกเลิกแล้วก็ไม่ได้", s == 410, s)
check("ลบแล้วหายจากรายการของคนในหน่วยงาน",
      "โครงการของฝ่ายจัดซื้อ" not in titles(a2), titles(a2))
check("ลบแล้วหายจากรายการของเจ้าของเองด้วย",
      "โครงการของฝ่ายจัดซื้อ" not in titles(a1), titles(a1))
check("แต่ยังอยู่ในถังขยะของเจ้าของ",
      "โครงการของฝ่ายจัดซื้อ" in titles(a1, "?trash=true"), titles(a1, "?trash=true"))
check("ถังขยะเป็นของใครของมัน คนในหน่วยงานไม่เห็นของที่คนอื่นลบ",
      "โครงการของฝ่ายจัดซื้อ" not in titles(a2, "?trash=true"), titles(a2, "?trash=true"))

s, res = call("/boms/{}".format(pid), "DELETE", token=a1)
check("ลบซ้ำอันเดิม ระบบบอกว่าอยู่ในถังขยะแล้ว", s == 400, (s, res))

s, res = call("/boms/{}/restore".format(pid), "POST", token=a1)
check("กู้คืนจากถังขยะได้", s == 200, (s, res))
check("กู้โครงการแล้วใบขอราคากลับมาด้วย",
      res.get("rfqs_restored", 0) >= 1 and rfq_no in rfq_nos(a1), (res, rfq_nos(a1)))
s, back = call("/portal/{}".format(vendor_token), token=ADMIN)
check("ผู้ขายเปิดลิงก์เดิมได้อีกครั้งหลังกู้โครงการ",
      s == 200 and not back.get("cancelled"), (s, back))
check("กู้แล้วกลับมาให้คนในหน่วยงานเห็นเหมือนเดิม",
      "โครงการของฝ่ายจัดซื้อ" in titles(a2), titles(a2))

# ---------------------------------------------------------------- ลบถาวร
s, res = call("/boms/{}/purge".format(pid), "DELETE", token=ADMIN)
check("ลบถาวรทั้งที่ยังไม่ได้อยู่ในถังขยะ ทำไม่ได้ (กันกดพลาดครั้งเดียวหายถาวร)",
      s == 400 and "ถังขยะ" in str(res.get("detail", "")), (s, res))
call("/boms/{}".format(pid), "DELETE", token=a1)
s, res = call("/boms/{}/purge".format(pid), "DELETE", token=a1)
check("คนทั่วไปลบถาวรไม่ได้ แม้เป็นเจ้าของ", s == 403, (s, res))
s, res = call("/boms/{}/purge".format(pid), "DELETE", token=ADMIN)
check("admin ลบถาวรได้เมื่ออยู่ในถังขยะแล้ว", s == 200, (s, res))
check("ลบถาวรแล้วล้างใบขอราคาที่ผูกอยู่ไปด้วย ไม่ทิ้งขยะกำพร้า",
      res.get("rfqs_deleted", 0) >= 1, res)
check("ไฟล์ที่ผูกกับใบพวกนั้นถูกลบออกจากฐานข้อมูลด้วย",
      res.get("files_deleted", 0) >= 1, res)
s, res2 = call("/boms/{}".format(pid), token=ADMIN)
check("ลบถาวรแล้วหายจากฐานข้อมูลจริง", s == 404, s)
s, res3 = call("/rfqs/{}".format(rfq_id), token=ADMIN)
check("ใบขอราคาของโครงการนั้นก็หายไปจริง", s == 404, s)
s, res4 = call("/portal/{}".format(vendor_token), token=ADMIN)
check("ลิงก์ของผู้ขายใช้ไม่ได้แล้วหลังลบถาวร", s == 404, s)

# เก็บกวาดโครงการที่ใช้ทดสอบ
call("/boms/{}".format(pid2), "DELETE", token=b1)
call("/boms/{}/purge".format(pid2), "DELETE", token=ADMIN)

print("\n{} passed, {} failed".format(ok, fail))
sys.exit(1 if fail else 0)
