from fastapi import APIRouter

router = APIRouter(prefix="/oss", tags=["OSS"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "status": "ok"}
