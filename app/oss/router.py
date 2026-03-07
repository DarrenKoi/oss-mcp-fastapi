from fastapi import APIRouter

from app.oss.aps.router import router as aps_router
from app.oss.dec.router import router as dec_router
from app.oss.mtc.router import router as mtc_router

router = APIRouter(prefix="/oss", tags=["OSS"])

for child_router in (mtc_router, aps_router, dec_router):
    router.include_router(child_router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "status": "ok"}
