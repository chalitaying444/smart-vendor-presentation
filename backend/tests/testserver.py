"""รันแอปจริงบนฐานข้อมูลจำลอง (mongomock) เพื่อทดสอบทั้ง API และหน้าเว็บ

ใช้โค้ด backend ตัวจริงทุกบรรทัด เปลี่ยนแค่ปลายทางฐานข้อมูล
"""
import asyncio
import os
import pickle
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret-for-local-e2e-only")
os.environ.setdefault("FRONTEND_URL", "http://localhost:3100")
os.environ.setdefault("MONGODB_DB", "epicor_procurement")

SEED_FILE = os.environ.get("TEST_SEED", "/tmp/epicor_seed.pkl")
PORT = int(os.environ.get("TEST_PORT", "8000"))

from mongomock_motor import AsyncMongoMockClient   # noqa: E402

from app.db import mongodb                        # noqa: E402
from app.core.config import settings               # noqa: E402

_client = AsyncMongoMockClient()
_db = _client["epicor_procurement"]


async def _load_seed():
    with open(SEED_FILE, "rb") as fh:
        data = pickle.load(fh)
    for name, rows in data.items():
        if rows:
            await _db[name].insert_many(rows)
    # ผู้ใช้สำหรับทดสอบ
    from app.models.common import utcnow
    await _db[settings.USERS_COLLECTION].insert_one({
        "email": "buyer@precise.co.th", "name": "ทดสอบ จัดซื้อ", "role": "admin",
        "is_active": True, "created_at": utcnow(), "ms_oid": None,
    })
    print("seed loaded:", {k: await _db[k].count_documents({}) for k in data})


async def _fake_connect():
    mongodb.set_database(_db)
    await mongodb.ensure_indexes()


# แทนที่การเชื่อมต่อจริงด้วยฐานข้อมูลจำลอง
mongodb.connect_to_mongo = _fake_connect
mongodb.close_mongo_connection = lambda: asyncio.sleep(0)
mongodb.set_database(_db)

from app.main import app                            # noqa: E402

if __name__ == "__main__":
    import uvicorn

    asyncio.get_event_loop().run_until_complete(_load_seed())
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
