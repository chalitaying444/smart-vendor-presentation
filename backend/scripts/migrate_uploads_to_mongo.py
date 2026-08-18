"""ย้ายไฟล์ที่เคยเก็บบนดิสก์ (โฟลเดอร์ uploads) เข้า MongoDB — รันครั้งเดียว

    cd backend
    ..\\.venv\\Scripts\\python scripts\\migrate_uploads_to_mongo.py            # ดูก่อนว่าจะย้ายอะไร
    ..\\.venv\\Scripts\\python scripts\\migrate_uploads_to_mongo.py --commit   # ย้ายจริง

**ย้ายเฉพาะไฟล์แนบของผู้ขาย** เพราะเป็นไฟล์เดียวที่สร้างใหม่ไม่ได้
ส่วนใบขอราคาและงบประมาณที่เป็น Excel ระบบสร้างใหม่ให้เองอยู่แล้วเมื่อมีคนกดโหลด
จึงไม่ต้องย้าย — ย้ายไปก็ได้แค่ไฟล์เวอร์ชันเก่าที่อาจไม่ตรงกับข้อมูลปัจจุบัน

สคริปต์นี้ **ไม่ลบไฟล์ต้นทาง** ให้ตรวจว่าโหลดจากระบบได้ครบก่อน แล้วค่อยลบโฟลเดอร์
uploads เองทีหลัง
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings                # noqa: E402
from app.db import schema                           # noqa: E402
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database  # noqa: E402
from app.services import filestore                  # noqa: E402

COMMIT = "--commit" in sys.argv


async def main() -> None:
    await connect_to_mongo()
    db = get_database()

    quotes = await db[schema.RFQ_QUOTES].find({"attachments.0": {"$exists": True}}).to_list(None)
    moved = skipped = missing = 0

    for quote in quotes:
        attachments = quote.get("attachments") or []
        fresh = []
        changed = False

        for att in attachments:
            if att.get("file_id"):
                fresh.append(att)
                skipped += 1
                continue

            rel = att.get("relative_path") or ""
            source = (settings.upload_path / rel) if rel else None
            if not source or not source.exists():
                print("  ไม่พบไฟล์ต้นทาง: {} ({})".format(att.get("filename", "?"), rel or "ไม่มี path"))
                missing += 1
                fresh.append(att)       # เก็บรายการเดิมไว้ ไม่ลบทิ้งเงียบ ๆ
                continue

            print("  ย้าย {} ({:,} ไบต์)".format(att.get("filename", source.name), source.stat().st_size))
            moved += 1
            changed = True
            if not COMMIT:
                fresh.append(att)
                continue

            saved = await filestore.put(
                source.read_bytes(),
                filename=att.get("filename") or source.name,
                content_type=att.get("content_type", ""),
                kind="quotes",
                ref=quote.get("rfq_no", ""),
                meta={"migrated_from": rel},
            )
            fresh.append({
                "file_id": saved["file_id"],
                "url": saved["url"],       # ลิงก์ของผู้ขายถูกเขียนใหม่ตอนเปิดหน้า portal
                "filename": saved["filename"],
                "size": saved["size"],
                "content_type": saved["content_type"],
                "sha256": saved["sha256"],
                "uploaded_at": att.get("uploaded_at"),
            })

        if changed and COMMIT:
            await db[schema.RFQ_QUOTES].update_one(
                {"_id": quote["_id"]}, {"$set": {"attachments": fresh}}
            )

    print("\nไฟล์ที่ต้องย้าย {} · อยู่ในฐานข้อมูลแล้ว {} · หาไฟล์ต้นทางไม่เจอ {}".format(
        moved, skipped, missing))
    if not COMMIT:
        print("นี่เป็นการดูเฉย ๆ ยังไม่ได้เขียนอะไร — ใส่ --commit เพื่อย้ายจริง")
    else:
        print("ย้ายเรียบร้อย · ไฟล์ต้นทางยังอยู่ที่เดิม ตรวจว่าโหลดได้ครบแล้วค่อยลบโฟลเดอร์ uploads")

    await close_mongo_connection()


if __name__ == "__main__":
    asyncio.run(main())
