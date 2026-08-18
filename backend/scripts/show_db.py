"""ดูว่าข้อมูลถูกเก็บไว้ที่ไหนและมีอะไรอยู่บ้าง

รันจากโฟลเดอร์ backend:
    python scripts\\show_db.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402


def mask(uri: str) -> str:
    """ซ่อนรหัสผ่านก่อนพิมพ์ออกจอ"""
    if "@" not in uri:
        return uri
    head, tail = uri.split("@", 1)
    if ":" in head.split("//", 1)[-1]:
        scheme, cred = head.split("//", 1)
        user = cred.split(":", 1)[0]
        return f"{scheme}//{user}:****@{tail}"
    return uri


async def main() -> None:
    print("=" * 62)
    print("เซิร์ฟเวอร์ :", mask(settings.MONGODB_URI))
    print("database   :", settings.MONGODB_DB)
    print("collection :", settings.USERS_COLLECTION)
    print("=" * 62)

    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
    try:
        info = await client.admin.command("buildInfo")
        print("MongoDB version:", info.get("version"))
    except Exception as exc:
        print("เชื่อมต่อไม่สำเร็จ:", exc)
        return

    db = client[settings.MONGODB_DB]
    names = await db.list_collection_names()
    print("collections ใน database นี้:", names or "(ยังไม่มี)")

    col = db[settings.USERS_COLLECTION]
    total = await col.count_documents({})
    print(f"\nจำนวนผู้ใช้ทั้งหมด: {total}")

    print("\nindex ที่มี:")
    async for idx in col.list_indexes():
        print(f"  - {idx['name']}: {dict(idx['key'])}")

    if total:
        print("\n10 รายการล่าสุด:")
        print(f"  {'อีเมล':<38} {'สิทธิ์':<8} {'ชื่อ'}")
        print("  " + "-" * 70)
        async for doc in col.find({}, {"email": 1, "role": 1, "display_name": 1}).sort("created_at", -1).limit(10):
            print(f"  {doc.get('email', ''):<38} {doc.get('role', ''):<8} {doc.get('display_name') or '-'}")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
