from fastapi import APIRouter

router = APIRouter(prefix="/skewnono/v1", tags=["SKEWNONO"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "skewnono", "version": "v1", "status": "ok"}
