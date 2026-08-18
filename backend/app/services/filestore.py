"""เก็บไฟล์ไว้ใน MongoDB ไม่ใช่บนดิสก์ของเครื่องที่รันแอป

ทำไมย้ายเข้าฐานข้อมูล:

* **ไฟล์กับข้อมูลอยู่ที่เดียวกัน** — สำรองข้อมูลครั้งเดียวได้ครบ ย้ายเครื่อง/ย้ายเซิร์ฟเวอร์
  ก็ไม่ต้องคัดลอกโฟลเดอร์ ``uploads`` ตามไปด้วย และไม่มีกรณี "แถวในฐานข้อมูลมีอยู่
  แต่ไฟล์บนดิสก์หายไปแล้ว"
* **ปิดรูที่ไฟล์เปิดสาธารณะ** — เดิมโฟลเดอร์ uploads ถูก mount เป็น static ที่ ``/files``
  ใครเดา URL ถูกก็โหลดใบเสนอราคาของผู้ขายรายอื่นได้โดยไม่ต้องล็อกอิน
  ตอนนี้ต้องผ่าน endpoint ที่ตรวจสิทธิ์ก่อนเสมอ
* **ลบแล้วหายจริง** — เดิมลบไฟล์แนบออกจากใบเสนอราคา ตัวไฟล์ยังกองอยู่บนดิสก์ตลอดไป

รูปแบบการเก็บ (จงใจทำให้หน้าตาเหมือน GridFS จะได้ย้ายไปใช้ของจริงทีหลังได้ง่าย):

    app_files        1 เอกสาร = 1 ไฟล์ — ชื่อ ขนาด ชนิด เจ้าของ (ไม่มีเนื้อไฟล์)
    app_file_chunks  1 เอกสาร = เนื้อไฟล์ 1 ก้อน ก้อนละ 1 MB {file_id, n, data}

ที่ไม่ใช้ GridFS ของ pymongo ตรง ๆ เพราะชุดทดสอบรันบน mongomock ซึ่งไม่รองรับ GridFS
ถ้าใช้ ส่วนที่รับ-ส่งไฟล์ทั้งหมดจะกลายเป็นส่วนเดียวของระบบที่ไม่มีเทสต์ครอบเลย

**ลำดับการเขียนสำคัญ**: เขียนก้อนเนื้อไฟล์ให้ครบก่อน แล้วค่อยเขียนเอกสารกำกับเป็นอันสุดท้าย
ถ้าไฟดับกลางทางจะเหลือแค่ก้อนกำพร้าที่ไม่มีใครอ้างถึง (เก็บกวาดทีหลังได้)
ไม่ใช่ไฟล์ที่ "มีชื่ออยู่ในระบบแต่เนื้อไม่ครบ" ซึ่งอันตรายกว่ามาก —
ใบเสนอราคาที่เปิดได้แต่ขาดหน้าท้ายไป คนอ่านจะไม่รู้เลยว่าขาด
"""
import hashlib
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from bson import Binary, ObjectId
from fastapi import HTTPException, status

from app.db import schema
from app.db.mongodb import get_database
from app.models.common import utcnow

CHUNK_SIZE = 1024 * 1024        # 1 MB ต่อก้อน — เอกสาร Mongo หนึ่งอันจำกัดที่ 16 MB


def _oid(file_id: Any) -> ObjectId:
    try:
        return file_id if isinstance(file_id, ObjectId) else ObjectId(str(file_id))
    except Exception:       # noqa: BLE001
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบไฟล์")


async def put(
    data: bytes,
    *,
    filename: str,
    content_type: str = "",
    kind: str = "",
    ref: str = "",
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """เก็บไฟล์ลงฐานข้อมูล คืนข้อมูลกำกับไฟล์ (ไม่มีเนื้อไฟล์)

    kind/ref ใช้ตามหาไฟล์ทีหลัง เช่น kind="quote" ref=<rfq_no>
    """
    db = get_database()
    file_id = ObjectId()
    chunks = [
        {"file_id": file_id, "n": n, "data": Binary(data[i:i + CHUNK_SIZE])}
        for n, i in enumerate(range(0, len(data), CHUNK_SIZE))
    ] or [{"file_id": file_id, "n": 0, "data": Binary(b"")}]

    await db[schema.FILE_CHUNKS].insert_many(chunks)

    doc = {
        "_id": file_id,
        "filename": filename,
        "content_type": content_type or "application/octet-stream",
        "size": len(data),
        "chunk_size": CHUNK_SIZE,
        "chunk_count": len(chunks),
        "sha256": hashlib.sha256(data).hexdigest(),
        "kind": kind,
        "ref": ref,
        "meta": meta or {},
        "uploaded_at": utcnow(),
    }
    await db[schema.FILES].insert_one(doc)       # เขียนอันนี้เป็นอันสุดท้ายเสมอ
    return view(doc)


def view(doc: Dict[str, Any]) -> Dict[str, Any]:
    """รูปแบบที่เก็บลงเอกสารอื่น (ใบเสนอราคา / RFQ / BOM) และส่งให้หน้าเว็บ"""
    return {
        "file_id": str(doc["_id"]),
        "filename": doc.get("filename", ""),
        "content_type": doc.get("content_type", ""),
        "size": doc.get("size", 0),
        "sha256": doc.get("sha256", ""),
        "url": "/api/files/{}".format(doc["_id"]),
    }


async def stat(file_id: Any) -> Optional[Dict[str, Any]]:
    return await get_database()[schema.FILES].find_one({"_id": _oid(file_id)})


async def read(file_id: Any) -> Dict[str, Any]:
    """อ่านไฟล์กลับมาทั้งก้อน — คืน dict ที่มี ``data`` เป็น bytes

    ตรวจจำนวนก้อนกับขนาดทุกครั้ง ถ้าไม่ตรงจะโยน error ไม่ใช่คืนไฟล์ที่ขาดหาย
    ไฟล์ที่ขาดท้ายมักเปิดได้ตามปกติ คนดาวน์โหลดจึงไม่มีทางรู้ว่าได้ไม่ครบ
    """
    db = get_database()
    doc = await db[schema.FILES].find_one({"_id": _oid(file_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบไฟล์")

    rows: List[Dict[str, Any]] = await db[schema.FILE_CHUNKS].find(
        {"file_id": doc["_id"]}
    ).sort("n", 1).to_list(None)

    if len(rows) != doc.get("chunk_count", len(rows)):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "ไฟล์ {} เสียหาย — เนื้อไฟล์ควรมี {} ก้อน แต่พบ {} ก้อน".format(
                doc.get("filename", ""), doc.get("chunk_count"), len(rows)),
        )

    data = b"".join(bytes(r["data"]) for r in rows)
    if doc.get("size") is not None and len(data) != doc["size"]:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "ไฟล์ {} เสียหาย — ขนาดควรเป็น {} ไบต์ แต่อ่านได้ {} ไบต์".format(
                doc.get("filename", ""), doc["size"], len(data)),
        )
    return dict(doc, data=data)


async def delete(file_id: Any) -> bool:
    """ลบไฟล์ — ลบเอกสารกำกับก่อน เพื่อไม่ให้มีจังหวะที่ยังอ้างถึงไฟล์ที่เนื้อหายไปแล้ว"""
    db = get_database()
    oid = _oid(file_id)
    result = await db[schema.FILES].delete_one({"_id": oid})
    await db[schema.FILE_CHUNKS].delete_many({"file_id": oid})
    return result.deleted_count > 0


async def replace(old_file_id: Any, *args: Any, **kwargs: Any) -> Dict[str, Any]:
    """เก็บไฟล์ใหม่แล้วลบไฟล์เก่าทิ้ง — ใช้กับเอกสารที่สร้างใหม่ได้ (Excel ของ RFQ/BOM)

    เก็บอันใหม่ให้สำเร็จก่อนค่อยลบอันเก่า ถ้าสลับลำดับแล้วสร้างใหม่ล้มเหลว
    จะเหลือรายการที่ไม่มีไฟล์ให้โหลดเลย
    """
    fresh = await put(*args, **kwargs)
    if old_file_id:
        try:
            await delete(old_file_id)
        except HTTPException:
            pass        # ไฟล์เก่าไม่มีอยู่แล้วก็ถือว่าจบ
    return fresh


def response(stored: Dict[str, Any]):
    """ส่งไฟล์กลับให้เบราว์เซอร์ พร้อมชื่อไฟล์ที่ถูกต้องแม้ชื่อเป็นภาษาไทย

    ``Content-Disposition`` รับได้แต่ ASCII ชื่อไทยจึงต้องส่งสองแบบคู่กัน:
    ``filename=`` แบบถอดเป็น ASCII ไว้ให้โปรแกรมเก่า และ ``filename*=UTF-8''``
    ไว้ให้เบราว์เซอร์ปัจจุบัน — ถ้าใส่แต่ชื่อไทยดิบ ๆ ผู้ขายบางรายจะโหลดไม่ได้เลย
    """
    from fastapi.responses import Response

    name = stored.get("filename") or "download"
    ascii_name = name.encode("ascii", "ignore").decode().strip() or "download"
    disposition = "attachment; filename=\"{}\"; filename*=UTF-8''{}".format(
        ascii_name.replace('"', ""), quote(name),
    )
    return Response(
        content=stored["data"],
        media_type=stored.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": disposition,
                 "Content-Length": str(len(stored["data"]))},
    )
