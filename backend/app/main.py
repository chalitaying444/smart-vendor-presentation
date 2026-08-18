"""จุดเริ่มต้นของ Vendor App API

รัน:  python main.py                                       (จากโฟลเดอร์ backend)
หรือ: python -m uvicorn app.main:app --reload --port 8000

Swagger UI: http://localhost:8000/docs
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import auth, sourcing_router, users, vendors
from app.core.config import settings
from app.db import schema
from app.db.mongodb import close_mongo_connection, connect_to_mongo, get_database
from app.models.common import serialize
from app.services import snapshot

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

# pymongo ส่ง heartbeat ทุก 10 วินาที ถ้าเปิด DEBUG จะท่วมหน้าจอ
_mongo_level = logging.DEBUG if settings.MONGO_DEBUG_LOG else logging.WARNING
for _noisy in ("pymongo", "pymongo.topology", "pymongo.command", "pymongo.serverSelection",
               "pymongo.connection", "pymongo.client", "motor"):
    logging.getLogger(_noisy).setLevel(_mongo_level)

logger = logging.getLogger("vendor_app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s (env=%s)", settings.APP_NAME, __version__, settings.APP_ENV)
    try:
        await connect_to_mongo()
    except Exception as exc:
        # ให้แอปยังขึ้นได้แม้ Mongo ยังไม่พร้อม จะได้เปิด /health ดูสาเหตุได้
        logger.error("เชื่อมต่อ MongoDB ไม่สำเร็จ: %s", exc)
    else:
        # วอร์มข้อมูลสรุปไว้เบื้องหลัง — คนแรกที่เข้าเว็บจะได้ของพร้อมใช้เลย
        # ไม่ await เพื่อไม่ให้เซิร์ฟเวอร์ค้างรอตอนสตาร์ท
        if settings.SNAPSHOT_WARM_ON_START:
            from app.api.routes.catalog import SNAPSHOT_BUILDERS
            warm_task = asyncio.ensure_future(snapshot.warm(SNAPSHOT_BUILDERS))
    yield
    for task in (locals().get("warm_task"),):
        if task is not None and not task.done():
            task.cancel()
    await close_mongo_connection()
    logger.info("Shutdown complete")


DESCRIPTION = """
API สำหรับระบบ **Vendor App** — บริหารผู้ขาย สินค้า และงานจัดหา

* ยืนยันตัวตนด้วย **Microsoft Entra ID** (OpenID Connect + PKCE)
* ข้อมูลผู้ขาย สินค้า ราคา และรายการเคลื่อนไหว มาจากฐานข้อมูล `epicor_procurement`
  ซึ่งสคริปต์ ETL ดึงมาจาก Epicor ERPPRD (แอปนี้อ่านอย่างเดียว ไม่เขียนทับ)
* งานจัดหา: ค้นหาสินค้า → ดูราคาล่าสุดและผู้ขายที่เคยขาย → ออก RFQ → เทียบใบเสนอราคากับราคาเดิม

### ทดสอบผ่าน Swagger
1. เปิด `GET /api/auth/ms/login` ในเบราว์เซอร์เพื่อล็อกอินกับ Microsoft
2. ระบบจะตั้ง cookie ให้อัตโนมัติ แล้วเรียก API อื่นได้ทันที
3. หรือใช้ `POST /api/auth/token` (เฉพาะโหมด DEBUG) แล้วกด **Authorize**
"""

app = FastAPI(
    title=settings.APP_NAME,
    description=DESCRIPTION,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers  (ทุกเส้นทางอยู่ใต้ settings.API_PREFIX = /api)
# ---------------------------------------------------------------------------
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(users.router, prefix=settings.API_PREFIX)
app.include_router(vendors.router, prefix=settings.API_PREFIX)
app.include_router(sourcing_router, prefix=settings.API_PREFIX)

# ไฟล์แนบทั้งหมดเก็บใน MongoDB แล้ว (services/filestore.py) — ไม่มีโฟลเดอร์ static ให้ mount
# ที่ตัด mount /files ทิ้ง ไม่ใช่แค่เพราะไม่มีไฟล์บนดิสก์: ของเดิมเปิดสาธารณะ
# ใครเดา URL ถูกก็โหลดใบเสนอราคาของผู้ขายได้โดยไม่ต้องล็อกอิน
# ตอนนี้ทุกไฟล์ต้องผ่าน endpoint ที่ตรวจสิทธิ์ก่อน (/api/files/{id} หรือลิงก์ที่ผูกกับ token)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """ValueError ที่หลุดมาจาก service layer = ข้อมูลนำเข้าไม่ถูกต้อง"""
    return JSONResponse({"detail": str(exc)}, status_code=400)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
async def _health_payload():
    db_ok, db_error = True, None
    counts = {}
    try:
        db = get_database()
        await db.command("ping")
        for name in schema.EPICOR_COLLECTIONS:
            counts[name] = await db[name].count_documents({})
        counts[schema.RFQS] = await db[schema.RFQS].count_documents({})
    except Exception as exc:
        db_ok, db_error = False, str(exc)

    snapshots = {}
    if db_ok:
        try:
            snapshots = await snapshot.status()
        except Exception:
            snapshots = {}

    return {
        "status": "ok" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": __version__,
        "env": settings.APP_ENV,
        "database": {"connected": db_ok, "name": settings.MONGODB_DB, "error": db_error},
        "data": counts,
        "etl_ready": counts.get(schema.EP_ITEMS, 0) > 0 and counts.get(schema.EP_VENDORS, 0) > 0,
        "snapshots": snapshots,
        "etl_hint": (
            "" if counts.get(schema.EP_ITEMS, 0) > 0
            else "ยังไม่มีข้อมูล — รัน scripts/04_etl_to_mongodb.py ของโปรเจกต์ epicorExploreData ก่อน"
        ),
        "microsoft_login_configured": settings.ms_configured,
    }


@app.get("/health", tags=["system"], summary="ตรวจสถานะระบบ + จำนวนข้อมูล")
async def health():
    payload = await _health_payload()
    # payload มี datetime (เวลาที่คำนวณข้อมูลสรุป) ซึ่ง JSONResponse แปลงเองไม่ได้
    return JSONResponse(
        status_code=200 if payload["status"] == "ok" else 503,
        content=serialize(payload),
    )


@app.get(f"{settings.API_PREFIX}/health", tags=["system"], summary="ตรวจสถานะระบบ (ใต้ /api)")
async def api_health():
    return await health()


@app.get("/", tags=["system"], summary="ข้อมูลบริการ")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": __version__,
        "docs": "/docs",
        "frontend": settings.FRONTEND_URL,
        "microsoft_login_configured": settings.ms_configured,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=settings.DEBUG)
