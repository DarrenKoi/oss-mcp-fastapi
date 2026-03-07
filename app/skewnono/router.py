from fastapi import APIRouter

from app.skewnono.v1 import router as v1_router

router = APIRouter(prefix="/skewnono", tags=["SKEWNONO"])

router.include_router(v1_router)
