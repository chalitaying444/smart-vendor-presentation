"""รวม router ของงานจัดหาไว้ที่เดียว

    from app.api.routes import sourcing_router
    app.include_router(sourcing_router, prefix=settings.API_PREFIX)
"""
from fastapi import APIRouter

from app.api.routes import boms, catalog, deliveries, files, portal, rfqs

sourcing_router = APIRouter()
sourcing_router.include_router(catalog.router)
sourcing_router.include_router(deliveries.router)
sourcing_router.include_router(boms.router)
sourcing_router.include_router(rfqs.router)
sourcing_router.include_router(portal.router)
sourcing_router.include_router(files.router)

__all__ = ["sourcing_router"]
