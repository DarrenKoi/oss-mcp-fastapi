from fastapi import APIRouter

from app.oss.v1 import router as v1_router

router = APIRouter(prefix="/oss", tags=["OSS"])

router.include_router(v1_router)
