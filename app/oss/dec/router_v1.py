from fastapi import APIRouter

router = APIRouter(prefix="/oss/dec/v1", tags=["OSS DEC"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "module": "dec", "version": "v1", "status": "ok"}
