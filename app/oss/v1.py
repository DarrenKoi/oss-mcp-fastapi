from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["OSS"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "version": "v1", "status": "ok"}
