from fastapi import APIRouter

from app.common.ftp_proxy.v1 import router as v1_router

router = APIRouter(prefix="/ftp-proxy", tags=["FTP Proxy"])

router.include_router(v1_router)
