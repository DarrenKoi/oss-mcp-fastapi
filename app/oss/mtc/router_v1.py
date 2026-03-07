from fastapi import APIRouter

router = APIRouter(prefix="/oss/mtc/v1", tags=["OSS MTC"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "module": "mtc", "version": "v1", "status": "ok"}
