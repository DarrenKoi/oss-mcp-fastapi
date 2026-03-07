from fastapi import APIRouter

from app.oss.dec.v1 import router as v1_router

router = APIRouter(prefix="/oss/dec", tags=["OSS DEC"])

router.include_router(v1_router)
