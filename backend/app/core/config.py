"""Application settings loaded from E:\\vendor_app\\.env"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py -> core -> app -> backend -> <project root = E:\vendor_app>
BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent
ENV_FILE = ROOT_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # อ่าน E:\vendor_app\.env ก่อน แล้วค่อย backend\.env (ถ้ามี)
        env_file=(str(ENV_FILE), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- App ----------
    APP_NAME: str = "Vendor App API"
    APP_ENV: str = "development"
    DEBUG: bool = True
    MONGO_DEBUG_LOG: bool = False   # True = แสดง heartbeat log ของ pymongo ด้วย

    API_PREFIX: str = "/api"

    # ---------- ข้อมูลสรุปที่คำนวณล่วงหน้า ----------
    # หน้าภาพรวมต้องกวาดข้อมูลทั้งฐาน จึงคำนวณเก็บไว้แล้วใช้ซ้ำ
    # ข้อมูลต้นทางเปลี่ยนเฉพาะตอนรัน ETL วันละครั้งก็เพียงพอ
    SNAPSHOT_TTL_HOURS: float = 24
    SNAPSHOT_WARM_ON_START: bool = True
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000

    # ---------- MongoDB ----------
    # ฐานข้อมูลเดียวกับที่สคริปต์ ETL ของ epicorExploreData เขียนลงไป
    MONGODB_URI: str = "mongodb://localhost:27017/"
    MONGODB_DB: str = "epicor_procurement"
    # ผู้ใช้ของแอปเก็บแยกจาก collection ของ ETL — ถ้าใช้ชื่อ "users" เฉย ๆ ยังปลอดภัย
    # แต่ตั้ง app_users ไว้ให้ชัดว่าใครเป็นเจ้าของ
    USERS_COLLECTION: str = "app_users"

    # ---------- JWT (session ของแอปเราเอง) ----------
    JWT_SECRET: str = "change-me-please-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 8
    SESSION_COOKIE_NAME: str = "vendor_session"
    COOKIE_SECURE: bool = False       # ตั้งเป็น True เมื่อขึ้น production (https)
    COOKIE_SAMESITE: str = "lax"

    # ---------- Microsoft Entra ID (Azure AD) ----------
    MS_TENANT_ID: str = ""
    MS_CLIENT_ID: str = ""
    MS_CLIENT_SECRET: str = ""
    MS_REDIRECT_URI: str = "http://localhost:8000/api/auth/ms/callback"
    MS_SCOPES: str = "openid profile email User.Read"

    # ---------- Frontend ----------
    FRONTEND_URL: str = "http://localhost:3000"
    CORS_ORIGINS: str = "http://localhost:3000"

    # ---------- ผู้ใช้ที่ให้เป็น admin ตั้งแต่ล็อกอินครั้งแรก ----------
    INITIAL_ADMIN_EMAILS: str = ""

    # ---------- เงื่อนไขที่ผู้ขายต้องรับทราบก่อนเสนอราคา ----------
    # แก้ข้อความได้ใน .env (คั่นแต่ละข้อด้วย |) และเลื่อนเวอร์ชันเมื่อแก้เนื้อหา
    # เพื่อให้บันทึกได้ว่าผู้ขายรับทราบเงื่อนไข "ฉบับไหน"
    PORTAL_TERMS_VERSION: str = "1.0"
    PORTAL_TERMS: str = ""

    # ---------- ไฟล์แนบฝั่ง sourcing (ไฟล์ BOM, ใบขอราคา, ใบเสนอราคาจากผู้ขาย) ----------
    # ไฟล์ที่อัปโหลดเก็บใน MongoDB แล้ว (services/filestore.py)
    # ค่านี้เหลือไว้ให้ scripts/migrate_uploads_to_mongo.py หาไฟล์เก่าที่ยังอยู่บนดิสก์เจอ
    UPLOAD_DIR: str = ""            # ว่าง = ใช้ <backend>\\uploads
    MAX_UPLOAD_MB: int = 20

    @property
    def portal_terms(self) -> list:
        """ข้อความเงื่อนไขที่แสดงบนหน้าผู้ขาย

        ค่าเริ่มต้นเป็นเงื่อนไขมาตรฐานของใบขอราคา — ฝ่ายจัดซื้อแก้ได้ที่ .env
        โดยไม่ต้องแก้โค้ด
        """
        if self.PORTAL_TERMS.strip():
            return [t.strip() for t in self.PORTAL_TERMS.split("|") if t.strip()]
        return [
            "ราคาที่เสนอเป็นราคาต่อหน่วย ยังไม่รวมภาษีมูลค่าเพิ่ม เว้นแต่ระบุไว้เป็นอย่างอื่น",
            "ราคารวมค่าขนส่งถึงสถานที่ส่งมอบที่ระบุไว้แล้ว",
            "กรุณายืนราคาไม่น้อยกว่า 30 วันนับจากวันที่เสนอ",
            "กำหนดส่งมอบที่ระบุ นับจากวันที่ผู้ซื้อออกใบสั่งซื้อ (PO)",
            "การเสนอราคานี้ไม่ผูกพันให้ผู้ซื้อต้องสั่งซื้อ และผู้ซื้อขอสงวนสิทธิ์ในการพิจารณา",
            "ข้อมูลในใบขอราคานี้เป็นความลับ กรุณาไม่เปิดเผยต่อบุคคลภายนอก",
            "ลิงก์นี้ออกให้บริษัทท่านโดยเฉพาะ กรุณาไม่ส่งต่อให้ผู้อื่น",
        ]

    @property
    def upload_path(self) -> Path:
        path = Path(self.UPLOAD_DIR) if self.UPLOAD_DIR else (BACKEND_DIR / "uploads")
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def ms_authority(self) -> str:
        tenant = self.MS_TENANT_ID or "common"
        return f"https://login.microsoftonline.com/{tenant}"

    @property
    def ms_authorize_url(self) -> str:
        return f"{self.ms_authority}/oauth2/v2.0/authorize"

    @property
    def ms_token_url(self) -> str:
        return f"{self.ms_authority}/oauth2/v2.0/token"

    @property
    def ms_jwks_url(self) -> str:
        return f"{self.ms_authority}/discovery/v2.0/keys"

    @property
    def ms_issuers(self) -> list[str]:
        return [
            f"https://login.microsoftonline.com/{self.MS_TENANT_ID}/v2.0",
            f"https://sts.windows.net/{self.MS_TENANT_ID}/",
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def scope_list(self) -> list[str]:
        return [s.strip() for s in self.MS_SCOPES.split() if s.strip()]

    @property
    def admin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.INITIAL_ADMIN_EMAILS.split(",") if e.strip()]

    @property
    def ms_configured(self) -> bool:
        return bool(self.MS_TENANT_ID and self.MS_CLIENT_ID and self.MS_CLIENT_SECRET)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
