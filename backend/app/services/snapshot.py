"""ข้อมูลสรุปที่คำนวณล่วงหน้า เก็บไว้ที่เดียว อัปเดตวันละครั้ง

หน้าภาพรวมต้องกวาดทั้ง ``items`` / ``vendors`` / ``transactions`` (~195,000 แถว)
ทุกครั้งที่เปิด ซึ่งเป็นงานหนักที่ให้คำตอบเดิมทั้งวัน เพราะข้อมูลต้นทางเปลี่ยน
ก็ต่อเมื่อรัน ETL รอบใหม่เท่านั้น

จึงคำนวณครั้งเดียวแล้วเก็บผลไว้ใน ``app_snapshots`` (collection ของแอป ไม่ใช่ของ ETL)
แล้วอ่านซ้ำจากที่นั่น จนกว่าจะเกินอายุที่กำหนด (ค่าเริ่มต้น 24 ชั่วโมง)

**สิ่งที่ตั้งใจให้เป็น**

- ผู้ใช้ *ไม่เคย* ต้องรอการคำนวณของคนอื่น — ถ้าของเก่าหมดอายุแล้วแต่ยังคำนวณไม่เสร็จ
  จะได้ของเก่าไปใช้ก่อนทันที พร้อมธง ``stale`` ให้หน้าบ้านบอกผู้ใช้ว่ากำลังอัปเดตอยู่
- คำนวณพร้อมกันได้ทีละคนต่อหนึ่งชุดข้อมูล (asyncio.Lock) ไม่ให้หลายคนไปกวาดพร้อมกัน
- ไม่ต้องพึ่ง scheduler ภายนอก — เช็กอายุตอนมีคนเรียก และวอร์มให้ตอนเปิดเซิร์ฟเวอร์
"""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Awaitable, Callable, Dict, Optional

from app.core.config import settings
from app.db import schema
from app.db.mongodb import get_database
from app.models.common import utcnow

logger = logging.getLogger(__name__)

_locks: Dict[str, asyncio.Lock] = {}


def _lock(name: str) -> asyncio.Lock:
    if name not in _locks:
        _locks[name] = asyncio.Lock()
    return _locks[name]


async def read(name: str) -> Optional[Dict[str, Any]]:
    return await get_database()[schema.SNAPSHOTS].find_one({"_id": name})


async def _save(name: str, payload: Any, seconds: float) -> Dict[str, Any]:
    doc = {
        "_id": name,
        "payload": payload,
        "built_at": utcnow(),
        "build_seconds": round(seconds, 3),
    }
    await get_database()[schema.SNAPSHOTS].replace_one({"_id": name}, doc, upsert=True)
    return doc


def _age_hours(doc: Optional[Dict[str, Any]]) -> Optional[float]:
    if not doc or not doc.get("built_at"):
        return None
    built = doc["built_at"]
    if built.tzinfo is None:
        built = built.replace(tzinfo=utcnow().tzinfo)
    return (utcnow() - built).total_seconds() / 3600


async def build(name: str, builder: Callable[[], Awaitable[Any]]) -> Dict[str, Any]:
    """คำนวณใหม่แล้วบันทึกทับ — ใช้ตอนวอร์มหรือตอนผู้ใช้กดรีเฟรชเอง"""
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    payload = await builder()
    doc = await _save(name, payload, loop.time() - t0)
    logger.info("สร้างข้อมูลสรุป '%s' ใหม่แล้ว (%.2f วินาที)", name, doc["build_seconds"])
    return doc


async def get(
    name: str,
    builder: Callable[[], Awaitable[Any]],
    ttl_hours: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """อ่านข้อมูลสรุป — คำนวณใหม่เฉพาะเมื่อยังไม่มี หรือเกินอายุ

    คืน ``{data, built_at, age_hours, stale, from_cache}``
    """
    ttl = settings.SNAPSHOT_TTL_HOURS if ttl_hours is None else ttl_hours
    doc = await read(name)
    age = _age_hours(doc)
    expired = force or doc is None or age is None or age >= ttl

    if not expired:
        return _view(doc, stale=False, from_cache=True)

    lock = _lock(name)
    if lock.locked() and doc is not None:
        # มีคนกำลังคำนวณอยู่ — ส่งของเก่าไปใช้ก่อน ดีกว่าให้ผู้ใช้นั่งรอ
        return _view(doc, stale=True, from_cache=True)

    async with lock:
        # อาจมีคนคำนวณเสร็จไปแล้วระหว่างที่รอคิว
        latest = await read(name)
        latest_age = _age_hours(latest)
        if not force and latest is not None and latest_age is not None and latest_age < ttl:
            return _view(latest, stale=False, from_cache=True)
        try:
            fresh = await build(name, builder)
        except Exception as exc:
            logger.exception("สร้างข้อมูลสรุป '%s' ล้มเหลว: %s", name, exc)
            if doc is not None:
                return _view(doc, stale=True, from_cache=True)
            raise
        return _view(fresh, stale=False, from_cache=False)


def _view(doc: Dict[str, Any], stale: bool, from_cache: bool) -> Dict[str, Any]:
    age = _age_hours(doc)
    return {
        "data": doc.get("payload"),
        "built_at": doc.get("built_at"),
        "age_hours": round(age, 2) if age is not None else None,
        "build_seconds": doc.get("build_seconds"),
        "stale": stale,
        "from_cache": from_cache,
        "next_refresh_at": (
            doc["built_at"] + timedelta(hours=settings.SNAPSHOT_TTL_HOURS)
            if doc.get("built_at") else None
        ),
    }


async def warm(names: Dict[str, Callable[[], Awaitable[Any]]]) -> None:
    """วอร์มตอนเปิดเซิร์ฟเวอร์ — คนแรกที่เข้าเว็บจะได้ของพร้อมใช้เลย

    ทำแบบเงียบ ๆ ถ้าพลาดก็ไม่ทำให้เซิร์ฟเวอร์ล้ม เดี๋ยวมีคนเรียกก็คำนวณเอง
    """
    for name, builder in names.items():
        try:
            doc = await read(name)
            age = _age_hours(doc)
            if doc is not None and age is not None and age < settings.SNAPSHOT_TTL_HOURS:
                logger.info("ข้อมูลสรุป '%s' ยังใหม่อยู่ (%.1f ชม.) ไม่ต้องคำนวณใหม่", name, age)
                continue
            await build(name, builder)
        except Exception as exc:
            logger.warning("วอร์มข้อมูลสรุป '%s' ไม่สำเร็จ: %s", name, exc)


async def status() -> Dict[str, Any]:
    """สถานะของข้อมูลสรุปทุกชุด — ใช้ใน /health และหน้าตั้งค่า"""
    rows = await get_database()[schema.SNAPSHOTS].find({}, {"payload": 0}).to_list(50)
    return {
        r["_id"]: {
            "built_at": r.get("built_at"),
            "age_hours": round(_age_hours(r) or 0, 2),
            "build_seconds": r.get("build_seconds"),
        }
        for r in rows
    }
