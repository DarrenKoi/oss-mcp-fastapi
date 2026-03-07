from fastapi import APIRouter

router = APIRouter(prefix="/oss/mtc", tags=["OSS MTC"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "module": "mtc", "status": "ok"}
