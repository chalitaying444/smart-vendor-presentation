"""สร้าง/ปรับโครงสร้างฐานข้อมูลเวนเดอร์บน MongoDB

รันจากโฟลเดอร์ backend:
    python scripts\\design_db.py            # สร้าง collection + validator + index
    python scripts\\design_db.py --show     # ดูโครงสร้างปัจจุบันเฉย ๆ ไม่แก้อะไร
    python scripts\\design_db.py --drop     # ลบ collection เวนเดอร์แล้วสร้างใหม่ (ข้อมูลหาย!)

ตารางที่สร้าง
    vendors             1 เอกสาร = 1 ผู้ขาย  (_id = vendor_id)
    vendor_products     1 เอกสาร = 1 รายการสินค้า/บริการของผู้ขาย
    product_categories  ตารางหมวดสินค้า      (_id = category_code)
    vendor_contacts     รายชื่อผู้ติดต่อของแต่ละบริษัท
    users               ผู้ใช้ระบบ (มีอยู่แล้ว)
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import schema  # noqa: E402

VENDOR_COLLECTIONS = [schema.VENDORS, schema.VENDOR_PRODUCTS, schema.PRODUCT_CATEGORIES, schema.CONTACTS]


def mask(uri: str) -> str:
    if "@" not in uri:
        return uri
    head, tail = uri.split("@", 1)
    scheme, cred = head.split("//", 1)
    return f"{scheme}//{cred.split(':', 1)[0]}:****@{tail}"


async def show(db) -> None:
    print(f"\ndatabase: {settings.MONGODB_DB}")
    names = sorted(await db.list_collection_names())
    if not names:
        print("  (ยังไม่มี collection)")
        return
    for name in names:
        count = await db[name].count_documents({})
        print(f"\n  ● {name}  —  {count:,} เอกสาร")
        async for idx in db[name].list_indexes():
            keys = ", ".join(f"{k}:{v}" for k, v in idx["key"].items())
            flags = " UNIQUE" if idx.get("unique") else ""
            print(f"      index {idx['name']:<22} ({keys}){flags}")


async def apply_schema(db, drop: bool) -> None:
    existing = set(await db.list_collection_names())

    if drop:
        for name in VENDOR_COLLECTIONS:
            if name in existing:
                await db[name].drop()
                print(f"  ลบ collection '{name}' แล้ว")
        existing -= set(VENDOR_COLLECTIONS)

    for name in [settings.USERS_COLLECTION] + VENDOR_COLLECTIONS:
        validator = schema.VALIDATORS.get(name)
        if name not in existing:
            kwargs = {"validator": validator, "validationLevel": "moderate"} if validator else {}
            await db.create_collection(name, **kwargs)
            print(f"  สร้าง collection '{name}'" + (" (พร้อม validator)" if validator else ""))
        elif validator:
            await db.command({"collMod": name, "validator": validator, "validationLevel": "moderate"})
            print(f"  อัปเดต validator ของ '{name}'")

    for logical_name, indexes in schema.INDEXES.items():
        name = settings.USERS_COLLECTION if logical_name == schema.USERS else logical_name
        col = db[name]
        for idx_name, keys, opts in indexes:
            try:
                await col.create_index(keys, name=idx_name, **opts)
                print(f"  index {name}.{idx_name}")
            except Exception as exc:
                print(f"  ! index {name}.{idx_name} ไม่สำเร็จ: {exc}")


async def main() -> None:
    ap = argparse.ArgumentParser(description="สร้างโครงสร้างฐานข้อมูลเวนเดอร์")
    ap.add_argument("--show", action="store_true", help="แสดงโครงสร้างปัจจุบันเท่านั้น")
    ap.add_argument("--drop", action="store_true", help="ลบ collection เวนเดอร์ทิ้งก่อนสร้างใหม่")
    args = ap.parse_args()

    print("=" * 66)
    print("เซิร์ฟเวอร์ :", mask(settings.MONGODB_URI))
    print("database   :", settings.MONGODB_DB)
    print("=" * 66)

    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=8000)
    db = client[settings.MONGODB_DB]
    try:
        await client.admin.command("ping")
    except Exception as exc:
        print("เชื่อมต่อ MongoDB ไม่สำเร็จ:", exc)
        sys.exit(1)

    if args.show:
        await show(db)
    else:
        if args.drop:
            answer = input("จะลบข้อมูลเวนเดอร์ทั้งหมด พิมพ์ 'yes' เพื่อยืนยัน: ")
            if answer.strip().lower() != "yes":
                print("ยกเลิก")
                client.close()
                return
        await apply_schema(db, drop=args.drop)
        await show(db)
        print("\nเสร็จเรียบร้อย — ขั้นต่อไป: python scripts\\import_data.py")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
