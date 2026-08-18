"""ตัวช่วยรันเซิร์ฟเวอร์: เปิด PowerShell ที่โฟลเดอร์ backend แล้วสั่ง

    python main.py

เทียบเท่ากับ:  python -m uvicorn app.main:app --reload
Swagger UI: http://localhost:8000/docs
"""
import uvicorn

from app.core.config import settings

if __name__ == "__main__":
    print(f"Swagger UI -> http://localhost:{settings.BACKEND_PORT}/docs")
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.BACKEND_PORT,
        reload=settings.DEBUG,
    )
