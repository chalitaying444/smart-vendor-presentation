"""นิยาม collection ที่ระบบใช้ — ฐานข้อมูล ``epicor_procurement``

แบ่งชัดเจนเป็นสองกลุ่ม เพราะเจ้าของข้อมูลคนละคน:

**กลุ่มที่ ETL เป็นเจ้าของ (อ่านอย่างเดียว)**
    สร้างและล้างใหม่โดย ``scripts/04_etl_to_mongodb.py`` ของโปรเจกต์ epicorExploreData
    แอปนี้ห้ามเขียนทับเด็ดขาด เพราะการรัน ETL รอบถัดไปจะล้างทิ้งทั้งหมด

        vendors           ผู้ขาย 1 ราย        _id = "PSP|21010236"
        items             สินค้า 1 รหัส       _id = "PSP|01-016-02-04-008"
        item_last_price   ประวัติราคา 1 รหัส  _id เดียวกับ items
        transactions      รายการเคลื่อนไหว    PO / รับของ / ใบแจ้งหนี้
        etl_runs          ประวัติการรัน ETL
        deliveries        งวดส่งของ 1 งวด     _id = "PSP|REL|<PO>|<Line>|<Rel>"
        vendor_delivery   สรุป OTD ของผู้ขาย  _id = "PSP|<VendorID>"

**กลุ่มที่แอปเป็นเจ้าของ (อ่าน-เขียน)**
    ตั้งชื่อขึ้นต้นด้วย ``app_`` หรือ ``rfq_`` เพื่อไม่ให้ชนกับชื่อของ ETL
    ถ้าใช้ชื่อ ``items``/``vendors`` ซ้ำ ข้อมูลของแอปจะหายทุกครั้งที่รัน ETL
"""
from pymongo import ASCENDING, DESCENDING

# --------------------------------------------------------------- ETL (read-only)
EP_VENDORS = "vendors"
EP_ITEMS = "items"
EP_LAST_PRICE = "item_last_price"
EP_TRANSACTIONS = "transactions"
EP_RUNS = "etl_runs"
# สร้างโดย scripts/05_delivery_performance.py --to-mongo
EP_DELIVERIES = "deliveries"            # 1 เอกสาร = 1 งวดส่งของ (PO Release)
EP_VENDOR_DELIVERY = "vendor_delivery"  # 1 เอกสาร = สรุปการส่งตรงเวลาของผู้ขาย 1 ราย

EPICOR_COLLECTIONS = [
    EP_VENDORS, EP_ITEMS, EP_LAST_PRICE, EP_TRANSACTIONS, EP_RUNS,
    EP_DELIVERIES, EP_VENDOR_DELIVERY,
]

# ชนิดเอกสารใน transactions
DOC_PO = "PO_LINE"
DOC_RECEIPT = "RECEIPT_LINE"
DOC_INVOICE = "AP_INVOICE_LINE"

DOC_TYPE_LABEL = {
    DOC_PO: "ใบสั่งซื้อ",
    DOC_RECEIPT: "รับของ",
    DOC_INVOICE: "ใบแจ้งหนี้",
}

# --------------------------------------------------------------- App (read-write)
USERS = "app_users"
RFQS = "rfqs"
RFQ_INVITES = "rfq_invites"
RFQ_QUOTES = "rfq_quotes"
VENDOR_ITEMS = "app_vendor_items"      # ราคาที่ชนะ RFQ — ใช้เป็นราคาอ้างอิงรอบถัดไป
VENDOR_OVERRIDES = "app_vendor_notes"  # สถานะอนุมัติ/เรตติ้ง/โน้ตที่ทีมจัดซื้อเพิ่มเอง
COUNTERS = "app_counters"
AUDIT_LOGS = "app_audit_logs"
SNAPSHOTS = "app_snapshots"            # ข้อมูลสรุปที่คำนวณล่วงหน้า อัปเดตวันละครั้ง
BOMS = "app_boms"                      # BOM ของโครงการ + ผลจับคู่สินค้าและงบประมาณเบื้องต้น
FILES = "app_files"                    # ข้อมูลกำกับไฟล์ที่อัปโหลด/สร้าง (ไม่มีเนื้อไฟล์)
FILE_CHUNKS = "app_file_chunks"        # เนื้อไฟล์ ตัดเป็นก้อนละ 1 MB (ดู services/filestore.py)

APP_COLLECTIONS = [
    USERS, RFQS, RFQ_INVITES, RFQ_QUOTES,
    VENDOR_ITEMS, VENDOR_OVERRIDES, COUNTERS, AUDIT_LOGS, SNAPSHOTS, BOMS,
    FILES, FILE_CHUNKS,
]

# --------------------------------------------------------------- Index
# สร้างเฉพาะ collection ของแอป — ของ ETL ถูกสร้าง index ไว้แล้วตอนรัน ETL
APP_INDEXES = {
    USERS: [
        ("uq_email", [("email", ASCENDING)], {"unique": True}),
        ("uq_ms_oid", [("ms_oid", ASCENDING)],
         {"unique": True, "partialFilterExpression": {"ms_oid": {"$type": "string"}}}),
        ("ix_created_at", [("created_at", ASCENDING)], {}),
    ],
    RFQS: [
        ("uq_rfq_no", [("rfq_no", ASCENDING)], {"unique": True}),
        ("ix_rfq_status", [("status", ASCENDING)], {}),
        ("ix_rfq_created", [("created_at", DESCENDING)], {}),
    ],
    RFQ_INVITES: [
        ("uq_invite_token", [("token", ASCENDING)], {"unique": True}),
        ("uq_rfq_vendor", [("rfq_id", ASCENDING), ("vendor_key", ASCENDING)], {"unique": True}),
    ],
    RFQ_QUOTES: [
        ("uq_quote_rfq_vendor", [("rfq_id", ASCENDING), ("vendor_key", ASCENDING)], {"unique": True}),
    ],
    VENDOR_ITEMS: [
        ("uq_vendor_item", [("vendor_key", ASCENDING), ("part_num", ASCENDING)], {"unique": True}),
        ("ix_vi_part", [("part_num", ASCENDING)], {}),
    ],
    VENDOR_OVERRIDES: [
        ("uq_override_vendor", [("vendor_key", ASCENDING)], {"unique": True}),
    ],
    AUDIT_LOGS: [
        ("ix_audit_at", [("at", DESCENDING)], {}),
    ],
    SNAPSHOTS: [
        ("ix_snapshot_built", [("built_at", DESCENDING)], {}),
    ],
    BOMS: [
        ("ix_bom_updated", [("updated_at", DESCENDING)], {}),
        ("ix_bom_no", [("bom_no", ASCENDING)], {}),
        # ใช้กรอง "โครงการที่คนนี้เห็นได้" ตั้งแต่ในฐานข้อมูล ไม่ใช่กรองทีหลังในแอป
        ("ix_bom_department", [("department", ASCENDING)], {}),
        ("ix_bom_owner", [("created_by", ASCENDING)], {}),
        ("ix_bom_assignees", [("assignees", ASCENDING)], {}),
        ("ix_bom_deleted", [("deleted_at", ASCENDING)], {}),
    ],
    FILES: [
        ("ix_file_ref", [("kind", ASCENDING), ("ref", ASCENDING)], {}),
        ("ix_file_uploaded", [("uploaded_at", DESCENDING)], {}),
    ],
    FILE_CHUNKS: [
        # unique เพื่อกันก้อนซ้ำลำดับเดียวกัน ซึ่งจะทำให้ไฟล์ที่ประกอบกลับมาเพี้ยน
        ("uq_chunk", [("file_id", ASCENDING), ("n", ASCENDING)], {"unique": True}),
    ],
}
