"""RFQ (ใบขอราคา) — ออกจาก BOM หรือเลือกสินค้าเอง แล้วส่งให้ผู้ขายหลายราย

ผู้ขายอ้างด้วย ``vendor_key`` (partner:xxx / erp:xxx)
"""
from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

RFQ_STATUSES = ("draft", "sent", "closed", "awarded", "cancelled")
INVITE_STATUSES = ("pending", "sent", "viewed", "quoted", "declined")


class RfqLineIn(BaseModel):
    part_num: str = Field(min_length=1, description="รหัสสินค้าใน Epicor เช่น 01-016-02-04-008")
    qty: float = Field(1, gt=0)
    uom: str = ""
    target_price: Optional[float] = Field(None, ge=0)
    required_date: Optional[date] = None
    remark: str = ""


class RfqLineOut(BaseModel):
    part_num: str
    item_code: str = ""
    name: str = ""
    description: str = ""
    manufacturer: str = ""
    mpn: str = ""
    category_code: str = ""
    specs: Dict[str, str] = Field(default_factory=dict)
    qty: float = 1
    uom: str = "PCS"
    target_price: Optional[float] = None
    required_date: Optional[datetime] = None
    remark: str = ""


class RfqCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: Optional[date] = Field(None, description="กำหนดยื่นราคา")
    currency: str = "THB"
    incoterm: str = ""
    payment_terms: str = ""
    delivery_place: str = ""
    note: str = ""
    lines: List[RfqLineIn] = Field(default_factory=list)
    vendor_keys: List[str] = Field(
        default_factory=list, description="เช่น epicor:21010236 (หรือส่งรหัสผู้ขายเปล่า ๆ ก็ได้)"
    )


class RfqUpdate(BaseModel):
    title: Optional[str] = None
    due_date: Optional[date] = None
    currency: Optional[str] = None
    incoterm: Optional[str] = None
    payment_terms: Optional[str] = None
    delivery_place: Optional[str] = None
    note: Optional[str] = None
    lines: Optional[List[RfqLineIn]] = None


class RfqOut(BaseModel):
    id: str
    rfq_no: str
    title: str
    status: str = "draft"
    due_date: Optional[datetime] = None
    currency: str = "THB"
    incoterm: str = ""
    payment_terms: str = ""
    delivery_place: str = ""
    note: str = ""
    lines: List[RfqLineOut] = Field(default_factory=list)
    vendor_count: int = 0
    quote_count: int = 0
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    sent_at: Optional[datetime] = None


# ---------------------------------------------------------------- invite
class RfqInviteIn(BaseModel):
    vendor_keys: List[str] = Field(min_length=1)
    contact_email_override: Dict[str, str] = Field(
        default_factory=dict, description="vendor_key -> อีเมลที่จะใช้แทนผู้ติดต่อหลัก"
    )


class RfqInviteOut(BaseModel):
    id: str
    rfq_id: str
    vendor_key: str
    source: str = ""
    vendor_id: str = ""
    vendor_name: str = ""
    contact_email: str = ""
    contact_name: str = ""
    status: str = "pending"
    token: str = ""
    portal_url: str = ""
    rfq_document_url: str = ""
    sent_at: Optional[datetime] = None
    viewed_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    has_quote: bool = False


class RfqSendRequest(BaseModel):
    message: str = Field("", description="ข้อความถึงผู้ขาย แนบไปในเนื้อหาใบขอราคา")
    vendor_keys: List[str] = Field(
        default_factory=list, description="ว่าง = ส่งให้ผู้ขายทุกรายที่เชิญไว้"
    )


# ---------------------------------------------------------------- quote
class QuoteLineIn(BaseModel):
    part_num: str
    unit_price: Optional[float] = Field(None, ge=0)
    moq: Optional[float] = Field(None, ge=0)
    lead_time_days: Optional[int] = Field(None, ge=0)
    offered_part_number: str = ""
    is_alternative: bool = Field(False, description="เสนอของเทียบเท่าแทนของที่ขอ")
    remark: str = ""
    no_quote: bool = Field(False, description="ไม่เสนอราคารายการนี้")


class QuoteSubmit(BaseModel):
    lines: List[QuoteLineIn] = Field(default_factory=list)
    currency: str = "THB"
    vat_percent: float = Field(7, ge=0, le=100)
    valid_until: Optional[date] = None
    payment_terms: str = ""
    incoterm: str = ""
    delivery_days: Optional[int] = Field(None, ge=0)
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    note: str = ""


class QuoteAttachment(BaseModel):
    """ไฟล์แนบ 1 ไฟล์ — เนื้อไฟล์อยู่ใน MongoDB ไม่ใช่บนดิสก์ (services/filestore.py)"""
    file_id: str = Field("", description="อ้างถึงเอกสารใน app_files")
    filename: str
    size: int
    content_type: str = ""
    sha256: str = ""
    uploaded_at: Optional[datetime] = None
    url: str = ""


class QuoteLineOut(QuoteLineIn):
    item_code: str = ""
    name: str = ""
    qty: float = 1
    uom: str = "PCS"
    amount: Optional[float] = None


class QuoteOut(BaseModel):
    id: str
    rfq_id: str
    rfq_no: str = ""
    vendor_key: str
    vendor_name: str = ""
    lines: List[QuoteLineOut] = Field(default_factory=list)
    currency: str = "THB"
    subtotal: float = 0
    vat_percent: float = 7
    vat_amount: float = 0
    total: float = 0
    valid_until: Optional[datetime] = None
    payment_terms: str = ""
    incoterm: str = ""
    delivery_days: Optional[int] = None
    contact_name: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    note: str = ""
    attachments: List[QuoteAttachment] = Field(default_factory=list)
    submitted_at: Optional[datetime] = None


class DeclineRequest(BaseModel):
    reason: str = ""


class AcceptTermsRequest(BaseModel):
    """ผู้ขายกดรับทราบเงื่อนไขก่อนเสนอราคา"""
    accepted: bool = Field(description="ต้องเป็น true เท่านั้นจึงจะบันทึก")
    accepted_by: str = Field("", max_length=120, description="ชื่อผู้กดรับทราบ (ถ้ากรอก)")


# ---------------------------------------------------------------- comparison
class ComparisonCell(BaseModel):
    vendor_key: str
    unit_price: Optional[float] = None
    amount: Optional[float] = None
    lead_time_days: Optional[int] = None
    moq: Optional[float] = None
    is_alternative: bool = False
    no_quote: bool = False
    is_lowest: bool = False
    remark: str = ""


class ComparisonRow(BaseModel):
    part_num: str
    item_code: str
    name: str
    qty: float
    uom: str
    target_price: Optional[float] = None
    cells: List[ComparisonCell] = Field(default_factory=list)
    lowest_vendor_key: Optional[str] = None
    lowest_amount: Optional[float] = None


class ComparisonVendor(BaseModel):
    vendor_key: str
    vendor_name: str
    source: str = ""
    status: str = "pending"
    currency: str = "THB"
    total: Optional[float] = None
    quoted_lines: int = 0
    delivery_days: Optional[int] = None
    payment_terms: str = ""
    attachment_count: int = 0
    submitted_at: Optional[datetime] = None


class ComparisonOut(BaseModel):
    rfq_id: str
    rfq_no: str
    title: str
    currency: str
    vendors: List[ComparisonVendor] = Field(default_factory=list)
    rows: List[ComparisonRow] = Field(default_factory=list)
    best_total_vendor_key: Optional[str] = None
    split_award_total: Optional[float] = None
    single_vendor_total: Optional[float] = None
    split_saving: Optional[float] = None


class AwardRequest(BaseModel):
    """ยืนยันผู้ชนะ — เลือกได้ทั้งใบ หรือแยกรายบรรทัด"""
    vendor_key: Optional[str] = None
    line_awards: Dict[str, str] = Field(default_factory=dict, description="part_num -> vendor_key")
    reason: str = ""


class CloseRequest(BaseModel):
    reason: str = ""


class RfqBulkRequest(BaseModel):
    """ยกเลิก/กู้คืนหลายใบในครั้งเดียว — ติ๊กเลือกจากหน้ารายการ

    ทำเป็น "รายการ id" ไม่ใช่ "ยกเลิกทั้งหมดที่ค้นเจอ" เพราะคำสั่งแบบหลังจะกวาด
    ใบที่ไม่ได้อยู่บนหน้าจอตอนนั้นไปด้วย คนกดไม่มีทางรู้ว่ายกเลิกอะไรไปกี่ใบ
    """
    rfq_ids: List[str] = Field(default_factory=list, min_length=1,
                               description="id ของใบที่ติ๊กเลือกไว้")
