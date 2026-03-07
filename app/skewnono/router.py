from fastapi import APIRouter

router = APIRouter(prefix="/skewnono", tags=["SKEWNONO"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "skewnono", "status": "ok"}
