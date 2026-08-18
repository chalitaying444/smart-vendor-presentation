"""BOM ของโครงการ → จับคู่กับสินค้าที่เคยซื้อ → ประมาณงบเบื้องต้น

รันบน Python 3.9 จึงใช้ Optional[...] แทน syntax `X | None`
"""
from typing import List, Optional

from pydantic import BaseModel, Field

# สถานะการจับคู่ของแต่ละบรรทัด
MATCH_AUTO = "auto"        # ระบบจับให้เอง
MATCH_MANUAL = "manual"    # คนเลือกเอง
MATCH_PRICE = "manual_price"  # ไม่มีในระบบ แต่กรอกราคาเอง
MATCH_NONE = "none"        # ยังไม่มีราคา

BOM_STATUSES = ("draft", "estimated", "rfq_sent", "closed")


class BomLineIn(BaseModel):
    name: str = Field(min_length=1, max_length=300, description="ชื่อ/รายละเอียดจาก BOM")
    qty: float = Field(1, gt=0)
    uom: str = ""
    part_hint: str = Field("", description="รหัสสินค้าถ้ามีอยู่แล้วใน BOM")
    remark: str = ""


class BomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200, description="ชื่อโครงการ")
    department: str = Field(
        "", max_length=80,
        description="หน่วยงานเจ้าของโครงการ — เว้นว่าง = หน่วยงานแรกของคนสร้าง",
    )
    note: str = ""
    currency: str = "THB"
    contingency_percent: float = Field(
        10, ge=0, le=100, description="เผื่อสำรอง (%) บวกทับยอดรวม"
    )
    vat_percent: float = Field(7, ge=0, le=100)
    lines: List[BomLineIn] = Field(default_factory=list)


class BomUpdate(BaseModel):
    title: Optional[str] = None
    department: Optional[str] = Field(None, max_length=80)
    note: Optional[str] = None
    contingency_percent: Optional[float] = Field(None, ge=0, le=100)
    vat_percent: Optional[float] = Field(None, ge=0, le=100)
    status: Optional[str] = None


class BomLinePatch(BaseModel):
    """แก้บรรทัดเดียว — ใช้ตอนคลิกรายตัวเพื่อเปลี่ยนสินค้าที่จับคู่"""
    name: Optional[str] = None
    qty: Optional[float] = Field(None, gt=0)
    uom: Optional[str] = None
    remark: Optional[str] = None
    part_num: Optional[str] = Field(
        None, description="เลือกสินค้าใหม่ให้บรรทัดนี้ · ส่ง \"\" เพื่อยกเลิกการจับคู่"
    )
    manual_price: Optional[float] = Field(
        None, ge=0, description="กรอกราคาเอง เมื่อไม่มีสินค้านี้ในระบบ"
    )
    clear_manual_price: bool = False


class BomParseRequest(BaseModel):
    text: str = Field("", description="วางข้อความจาก Excel (คั่นด้วย tab หรือ comma)")


class BomRfqRequest(BaseModel):
    title: str = ""
    vendor_keys: List[str] = Field(default_factory=list)
    only_matched: bool = True


class BomRfqItem(BaseModel):
    """ผู้ขายที่จะเชิญของ "หนึ่งรายการ" — ออกใบขอราคาแยกใบต่อรายการ"""
    line_no: int = Field(ge=1)
    vendor_keys: List[str] = Field(default_factory=list)
    title: str = ""


class BomRfqPerItemRequest(BaseModel):
    items: List[BomRfqItem] = Field(default_factory=list)
    group_by: str = Field(
        "vendor",
        pattern="^(vendor|item)$",
        description=(
            "vendor = ผู้ขายหนึ่งรายได้ใบเดียว รวมทุกรายการที่เลือกเขาไว้ (ค่าตั้งต้น) · "
            "item = หนึ่งรายการหนึ่งใบ ผู้ขายรายเดียวกันอาจได้หลายใบ"
        ),
    )
    note: str = ""
    allow_repeat: bool = Field(
        False,
        description=(
            "ยอมให้เชิญผู้ขายที่เคยถูกเชิญสำหรับรายการนั้นแล้วซ้ำอีกครั้ง "
            "ค่าตั้งต้นคือตัดออกให้ แล้วรายงานกลับมาใน repeated"
        ),
    )
    send: bool = Field(
        False, description="ออกแล้วส่งให้ผู้ขายเลย · ไม่ส่ง = เก็บเป็นร่างไว้ตรวจก่อน"
    )
    message: str = Field("", description="ข้อความถึงผู้ขาย ใช้เมื่อ send=true")


class BomAwardItem(BaseModel):
    """เลือกผู้ชนะของ "หนึ่งรายการ" — คนเลือกจากสินค้า ไม่ต้องจำว่าอยู่ในใบไหน"""
    line_no: int = Field(ge=1)
    vendor_key: str = Field(min_length=1)


class BomAwardRequest(BaseModel):
    awards: List[BomAwardItem] = Field(default_factory=list)
    reason: str = ""


class BomAssignRequest(BaseModel):
    """เพิ่ม/ถอดคนออกจากโครงการเป็นรายคน — ใช้ตอนต้องให้คนนอกหน่วยงานเข้ามาช่วย"""
    add: List[str] = Field(default_factory=list, description="อีเมลที่จะเพิ่ม")
    remove: List[str] = Field(default_factory=list, description="อีเมลที่จะถอดออก")
