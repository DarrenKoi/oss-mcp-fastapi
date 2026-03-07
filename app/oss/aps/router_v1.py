from fastapi import APIRouter

router = APIRouter(prefix="/oss/aps/v1", tags=["OSS APS"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "module": "aps", "version": "v1", "status": "ok"}
