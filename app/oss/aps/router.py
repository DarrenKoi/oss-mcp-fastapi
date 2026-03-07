from fastapi import APIRouter

router = APIRouter(prefix="/oss/aps", tags=["OSS APS"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "module": "aps", "status": "ok"}
