"""Pydantic schemas ของผู้ใช้ระบบ

หมายเหตุ: ไฟล์นี้รวมทั้งสคีมาของการล็อกอินแบบ local (LoginRequest/RegisterRequest)
และสคีมาที่ api/routes/auth.py + users.py ใช้ (UserOut/TokenResponse/…)
"""
from datetime import datetime
from typing import Annotated, Any, Dict, List, Literal, Optional

from bson import ObjectId
from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, EmailStr, Field

PyObjectId = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]

# "staff" กับ "buyer" หมายถึงระดับเดียวกัน (ดู api/deps.py ROLE_RANK)
# รับทั้งสองคำเพื่อไม่ให้ข้อมูลผู้ใช้เดิมที่เป็น staff อยู่แล้วใช้ไม่ได้
Role = Literal["admin", "staff", "buyer", "vendor", "viewer"]


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=120)
    role: str = "viewer"


class UserBase(BaseModel):
    email: EmailStr = Field(..., description="อีเมลผู้ใช้ (unique)")
    display_name: Optional[str] = Field(None, description="ชื่อที่แสดง")
    role: Role = Field("vendor", description="สิทธิ์การใช้งาน")
    is_active: bool = True
    departments: List[str] = Field(
        default_factory=list,
        description=(
            "หน่วยงานที่สังกัด — คนเดียวอยู่ได้หลายหน่วยงาน (admin เป็นคนกำหนด) "
            "ใช้ตัดสินว่าเห็นโครงการไหนได้บ้าง · หน่วยงานแรกคือค่าตั้งต้นตอนสร้างโครงการ"
        ),
    )


class UserCreate(UserBase):
    """ใช้สร้าง user จาก API (admin เท่านั้น)"""
    vendor_code: Optional[str] = None


class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    vendor_code: Optional[str] = None
    departments: Optional[List[str]] = Field(
        None, description="แทนที่รายชื่อหน่วยงานทั้งชุด (admin เท่านั้น)")


class UserOut(UserBase):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    # รับค่าจาก Mongo ที่เป็น `_id` แต่ส่งออกเป็น `id` ให้ frontend ใช้ง่าย
    id: PyObjectId = Field(
        validation_alias=AliasChoices("_id", "id"),
        serialization_alias="id",
        description="รหัสผู้ใช้ (MongoDB ObjectId)",
    )
    vendor_code: Optional[str] = None
    ms_oid: Optional[str] = Field(None, description="Object ID ของผู้ใช้ใน Microsoft Entra ID")
    ms_tenant_id: Optional[str] = None
    auth_provider: str = "microsoft"
    last_login_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class MessageResponse(BaseModel):
    detail: str


def serialize_user(doc: Dict[str, Any]) -> Dict[str, Any]:
    """แปลง _id (ObjectId) เป็น str ให้ pydantic ใช้ได้"""
    if doc and isinstance(doc.get("_id"), ObjectId):
        doc = {**doc, "_id": str(doc["_id"])}
    return doc


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
