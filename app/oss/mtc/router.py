from fastapi import APIRouter

from app.oss.mtc.v1 import router as v1_router

router = APIRouter(prefix="/oss/mtc", tags=["OSS MTC"])

router.include_router(v1_router)
