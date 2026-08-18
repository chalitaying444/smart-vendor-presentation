"""ค่าที่ชุดทดสอบฝั่ง API ใช้ร่วมกัน — เปลี่ยนได้ด้วย environment variable

ค่าเริ่มต้นชี้ไปที่ ``testserver.py`` ซึ่งรันบน mongomock ไม่ใช่ฐานข้อมูลจริง
จงใจให้ default ปลอดภัย: ถ้าใครเผลอรันชุดทดสอบบนเครื่อง production
มันจะไปยิงพอร์ตที่ไม่มีอะไรอยู่แล้วพัง ดีกว่าเงียบ ๆ ไปแก้ข้อมูลจริง
"""
import os

BASE = os.environ.get("TEST_API", "http://127.0.0.1:8000/api")
FRONTEND = os.environ.get("TEST_FRONTEND", "http://localhost:3100")
TOKEN_FILE = os.environ.get("TEST_TOKEN_FILE", "/tmp/tok")


def token() -> str:
    """โทเคนของผู้ใช้ทดสอบ — จาก TEST_TOKEN ก่อน ไม่มีค่อยอ่านจากไฟล์"""
    value = os.environ.get("TEST_TOKEN", "").strip()
    if value:
        return value
    try:
        with open(TOKEN_FILE, encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        raise SystemExit(
            "ไม่พบโทเคนทดสอบที่ {}\n"
            "ขอใหม่ด้วย: curl -s -X POST '{}/auth/token?email=buyer@precise.co.th' > {}"
            .format(TOKEN_FILE, BASE, TOKEN_FILE)
        )
