"""เชื่อมต่อ MongoDB (Motor / async) + สร้าง index ของฝั่งแอป

ระบบใช้ฐานข้อมูล ``epicor_procurement`` ร่วมกับสคริปต์ ETL แต่คนละ collection:
ETL เป็นเจ้าของ vendors / items / item_last_price / transactions (แอปอ่านอย่างเดียว)
ส่วนแอปเป็นเจ้าของ collection ที่ขึ้นต้นด้วย app_ และ rfq_

จึงสร้าง index เฉพาะของแอปเท่านั้น — ไม่ไปยุ่งกับ collection ของ ETL
เพราะ ETL สร้าง index ของตัวเองอยู่แล้ว และการรัน ETL รอบใหม่จะล้าง collection ทิ้ง
"""
from typing import Optional
import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import settings
from app.db import schema

logger = logging.getLogger(__name__)

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongo() -> None:
    global _client, _db
    _client = AsyncIOMotorClient(
        settings.MONGODB_URI, serverSelectionTimeoutMS=5000, uuidRepresentation="standard"
    )
    _db = _client[settings.MONGODB_DB]
    try:
        await _client.admin.command("ping")
        logger.info("Connected to MongoDB, database=%s", settings.MONGODB_DB)
    except Exception as exc:  # pragma: no cover
        logger.error("MongoDB connection failed: %s", exc)
        raise
    await ensure_indexes()
    await warn_if_no_etl_data()


async def close_mongo_connection() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client, _db = None, None


def get_database() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("MongoDB ยังไม่ถูกเชื่อมต่อ (เรียก connect_to_mongo ก่อน)")
    return _db


def set_database(db: AsyncIOMotorDatabase) -> None:
    """ใช้ตอนทดสอบ เพื่อฉีดฐานข้อมูลจำลองเข้ามาแทนของจริง"""
    global _db
    _db = db


def users_collection():
    return get_database()[settings.USERS_COLLECTION]


async def ensure_indexes() -> None:
    db = get_database()
    existing = set(await db.list_collection_names())

    for name, indexes in schema.APP_INDEXES.items():
        real_name = settings.USERS_COLLECTION if name == schema.USERS else name
        if real_name not in existing:
            try:
                await db.create_collection(real_name)
                logger.info("Created collection '%s'", real_name)
            except Exception:
                pass       # อีก worker อาจสร้างไปพร้อมกัน
        col = db[real_name]
        for idx_name, keys, opts in indexes:
            try:
                await col.create_index(keys, name=idx_name, **opts)
            except Exception as exc:
                logger.warning("create_index %s.%s failed: %s", real_name, idx_name, exc)


async def warn_if_no_etl_data() -> None:
    """เตือนให้ชัดตั้งแต่ตอนเปิดเซิร์ฟเวอร์ ถ้ายังไม่ได้รัน ETL

    อาการที่เจอบ่อยคือหน้าเว็บว่างเปล่าแล้วไล่หาสาเหตุไม่เจอ — ต้นเหตุจริงคือ
    ฐานข้อมูลปลายทางยังไม่มีข้อมูล เพราะยังไม่ได้รัน scripts/04_etl_to_mongodb.py
    """
    db = get_database()
    try:
        items = await db[schema.EP_ITEMS].count_documents({})
        vendors = await db[schema.EP_VENDORS].count_documents({})
    except Exception as exc:
        logger.warning("อ่านจำนวนข้อมูล Epicor ไม่ได้: %s", exc)
        return

    if items == 0 or vendors == 0:
        logger.warning(
            "ฐานข้อมูล '%s' ยังไม่มีข้อมูลจาก Epicor (items=%s, vendors=%s) — "
            "ให้รัน scripts/04_etl_to_mongodb.py ของโปรเจกต์ epicorExploreData ก่อน",
            settings.MONGODB_DB, items, vendors,
        )
    else:
        logger.info("ข้อมูล Epicor พร้อมใช้งาน: items=%s, vendors=%s", items, vendors)
