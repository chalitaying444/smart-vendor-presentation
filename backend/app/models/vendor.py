"""โมเดลฝั่งผู้ขาย

ข้อมูลผู้ขายตัวจริงมาจาก Epicor และเป็นแบบอ่านอย่างเดียว จึงไม่มีโมเดล "สร้าง/แก้ไขผู้ขาย"
มีเฉพาะส่วนที่ทีมจัดซื้อบันทึกทับได้เอง ซึ่งเก็บแยกใน ``app_vendor_notes``
"""
from typing import List, Optional

from pydantic import BaseModel, Field

APPROVAL_STATUSES = ("pending", "approved", "rejected", "on_hold")


class VendorContact(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    function: str = ""
    is_primary: bool = False


class VendorNoteUpdate(BaseModel):
    """สถานะภายในของผู้ขาย — ไม่กระทบข้อมูลต้นทางจาก Epicor"""
    approval_status: Optional[str] = Field(
        None, description=" / ".join(APPROVAL_STATUSES)
    )
    rating: Optional[float] = Field(None, ge=0, le=5)
    system_note: Optional[str] = None
    blocked: Optional[bool] = None
    preferred: Optional[bool] = None
    contacts: Optional[List[VendorContact]] = None


class VendorOut(BaseModel):
    """รูปแบบที่ API คืนกลับ — ชื่อฟิลด์เป็น snake_case ต่างจากเอกสารดิบของ ETL"""
    vendor_key: str
    vendor_id: str
    vendor_num: Optional[int] = None
    name: str = ""
    emails: List[str] = Field(default_factory=list)
    phones: List[str] = Field(default_factory=list)
    contacts: List[VendorContact] = Field(default_factory=list)
    currency: str = "THB"
    terms_code: str = ""
    tax_id: str = ""
    inactive: bool = False
    has_purchase: bool = False
    po_count: int = 0
    po_amount: float = 0
    distinct_parts: int = 0
    has_email: bool = False
