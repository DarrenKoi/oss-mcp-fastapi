from fastapi import APIRouter

router = APIRouter(prefix="/oss/dec", tags=["OSS DEC"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "oss", "module": "dec", "status": "ok"}
