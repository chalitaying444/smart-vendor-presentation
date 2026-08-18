"""นำเข้าข้อมูลเวนเดอร์เข้า MongoDB ด้วยมือ

ปกติ **ไม่ต้องรันสคริปต์นี้** — backend จะนำเข้าให้อัตโนมัติตอนเปิดเซิร์ฟเวอร์
ถ้าฐานข้อมูลยังว่าง (ปิดได้ด้วย AUTO_IMPORT=false ใน .env)

ใช้สคริปต์นี้เมื่อต้องการบังคับนำเข้าใหม่:
    python scripts\\import_data.py                    # upsert ทับของเดิม
    python scripts\\import_data.py --purge            # ลบของเก่าทิ้งก่อน
    python scripts\\import_data.py --dry-run          # ลองรัน ไม่เขียนฐานข้อมูล
    python scripts\\import_data.py --data-dir "E:\\vendor_app\\Data"

แหล่งข้อมูลหลัก : Partner Contact.xlsx
แหล่งข้อมูลเสริม: vendors.csv / vendor_products.csv / product_categories.csv
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import schema  # noqa: E402
from app.db.importer import run_import  # noqa: E402


def mask(uri: str) -> str:
    if "@" not in uri:
        return uri
    head, tail = uri.split("@", 1)
    scheme, cred = head.split("//", 1)
    return f"{scheme}//{cred.split(':', 1)[0]}:****@{tail}"


async def main() -> None:
    ap = argparse.ArgumentParser(description="นำเข้าข้อมูลเวนเดอร์เข้า MongoDB")
    ap.add_argument("--data-dir", default=str(settings.data_path))
    ap.add_argument("--dry-run", action="store_true", help="ลองรันโดยไม่เขียนฐานข้อมูล")
    ap.add_argument("--purge", action="store_true", help="ลบข้อมูลเดิมก่อนนำเข้า")
    args = ap.parse_args()

    print("=" * 68)
    print("เซิร์ฟเวอร์    :", mask(settings.MONGODB_URI))
    print("database      :", settings.MONGODB_DB)
    print("โฟลเดอร์ข้อมูล :", args.data_dir)
    print("โหมด          :", "DRY-RUN (ไม่เขียนจริง)" if args.dry_run else "เขียนจริง")
    print("=" * 68)

    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=8000)
    db = client[settings.MONGODB_DB]
    try:
        await client.admin.command("ping")
    except Exception as exc:
        print("เชื่อมต่อ MongoDB ไม่สำเร็จ:", exc)
        sys.exit(1)

    result = await run_import(db, Path(args.data_dir), purge=args.purge, dry_run=args.dry_run)

    if not result["ok"]:
        print("\nนำเข้าไม่สำเร็จ:")
        for n in result["notes"]:
            print("  -", n)
        client.close()
        sys.exit(1)

    c = result["counts"]
    print("\n" + "=" * 68)
    print("สรุปผลการนำเข้า")
    print("=" * 68)
    print(f"  บริษัท (vendors)          : {c['vendors']:>6}   <- Partner Contact.xlsx")
    print(f"  ผู้ติดต่อ                  : {c['contacts']:>6}")
    print(f"  สินค้า/บริการ             : {c['products']:>6}"
          f"   (โน้ตผู้ติดต่อ {c['products_from_contacts']} + ERP {c['products_from_erp']})")
    print(f"  หมวดสินค้า                : {c['categories']:>6}")
    print(f"  ผู้ขายจาก ERP (ข้อมูลเสริม) : {c['erp_suppliers']:>6}")
    print(f"  เติมข้อมูล ERP ได้         : {c['erp_matched']:>6} บริษัท  {result['matched_by']}")

    if not args.dry_run:
        print("\nคุณภาพข้อมูลที่ต้องตามเก็บ")
        ven = db[schema.VENDORS]
        for label, cond in [
            ("ยังไม่มีข้อมูล ERP (ที่อยู่/เลขภาษี)", {"has_erp": False}),
            ("ไม่มีเบอร์โทรของผู้ติดต่อเลย", {"phones": {"$size": 0}}),
            ("ไม่มีอีเมลเลย", {"emails": {"$size": 0}}),
            ("ยังไม่มีรายการสินค้า", {"product_count": 0}),
        ]:
            n = await ven.count_documents(cond)
            if n:
                print(f"  - {label:<38} {n:>4} บริษัท ({n * 100 / max(c['vendors'], 1):.0f}%)")

        print("\nยอดจริงในฐานข้อมูล")
        for name in (schema.VENDORS, schema.CONTACTS, schema.VENDOR_PRODUCTS,
                     schema.PRODUCT_CATEGORIES, schema.ERP_SUPPLIERS):
            print(f"  {name:<20} {await db[name].count_documents({}):>6,} เอกสาร")
    else:
        print("\n(DRY-RUN — ยังไม่ได้เขียนอะไรลงฐานข้อมูล)")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
