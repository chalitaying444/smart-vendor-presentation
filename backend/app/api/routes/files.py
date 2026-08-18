"""ดาวน์โหลดไฟล์ที่เก็บไว้ในฐานข้อมูล — สำหรับคนในบริษัทที่ล็อกอินแล้ว

ผู้ขายไม่ได้ใช้เส้นทางนี้ เขาโหลดผ่านลิงก์ที่ผูกกับ token ของตัวเองใน ``/api/portal/...``
ซึ่งตรวจว่าไฟล์นั้นอยู่ในใบเสนอราคาของเขาจริงก่อนเสมอ

เดิมโฟลเดอร์ ``uploads`` ถูกเปิดเป็น static ที่ ``/files`` — ใครเดา URL ถูกก็โหลด
ใบเสนอราคาของผู้ขายได้โดยไม่ต้องล็อกอิน เส้นทางนี้จึงต้องมี ``get_current_user`` เสมอ
"""
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user
from app.models.common import serialize
from app.services import filestore

router = APIRouter(prefix="/files", tags=["ไฟล์"])


@router.get("/{file_id}", summary="ดาวน์โหลดไฟล์")
async def download(file_id: str, _: Dict[str, Any] = Depends(get_current_user)):
    return filestore.response(await filestore.read(file_id))


@router.get("/{file_id}/info", summary="ดูข้อมูลไฟล์โดยไม่ต้องโหลดตัวไฟล์")
async def info(file_id: str, _: Dict[str, Any] = Depends(get_current_user)):
    """อ่านเฉพาะเอกสารกำกับ ไม่ดึงเนื้อไฟล์ — ใช้เช็กว่าไฟล์ยังอยู่ไหมโดยไม่ต้องโหลดทั้งก้อน"""
    doc = await filestore.stat(file_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบไฟล์")
    return serialize(dict(filestore.view(doc), uploaded_at=doc.get("uploaded_at"),
                          kind=doc.get("kind", ""), ref=doc.get("ref", "")))
