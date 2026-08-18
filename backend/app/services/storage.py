"""ตรวจไฟล์ที่อัปโหลดเข้ามา แล้วส่งต่อให้ ``filestore`` เก็บลง MongoDB

ไฟล์ไม่ถูกเขียนลงดิสก์อีกแล้ว — ดูเหตุผลใน ``services/filestore.py``
โมดูลนี้เหลือหน้าที่เดียวคือ **ด่านตรวจ**: นามสกุลที่รับ ขนาดที่รับ
และล้างชื่อไฟล์ที่ผู้ใช้ตั้งมาก่อนเก็บ (ชื่อจากผู้ใช้ต้องไม่มีผลต่อที่เก็บ)
"""
import re
from pathlib import PurePath
from typing import Any, Dict, Optional, Set

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.services import filestore

QUOTE_SUFFIXES = {".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".zip"}

_SAFE = re.compile(r"[^0-9A-Za-z._\-฀-๿ ]+")


def safe_filename(name: str) -> str:
    cleaned = _SAFE.sub("_", PurePath(name or "file").name).strip() or "file"
    return cleaned[:150]


async def save_upload(
    file: UploadFile,
    kind: str,
    allowed_suffixes: Optional[Set[str]] = None,
    ref: str = "",
) -> Dict[str, Any]:
    """ตรวจแล้วเก็บลงฐานข้อมูล คืน ``{file_id, filename, size, content_type, url}``"""
    original = safe_filename(file.filename or "upload")
    suffix = PurePath(original).suffix.lower()

    if allowed_suffixes and suffix not in allowed_suffixes:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "ไม่รองรับไฟล์นามสกุล {} — รองรับ: {}".format(
                suffix or "(ไม่มี)", ", ".join(sorted(allowed_suffixes))
            ),
        )

    data = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "ไฟล์ใหญ่เกิน {} MB".format(settings.MAX_UPLOAD_MB),
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "ไฟล์ว่างเปล่า")

    return await filestore.put(
        data,
        filename=original,
        content_type=file.content_type or "",
        kind=kind,
        ref=ref,
    )
