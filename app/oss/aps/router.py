from fastapi import APIRouter

from app.oss.aps.v1 import router as v1_router

router = APIRouter(prefix="/oss/aps", tags=["OSS APS"])

router.include_router(v1_router)
