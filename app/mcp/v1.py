from fastapi import APIRouter

router = APIRouter(prefix="/v1", tags=["MCP"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "mcp", "version": "v1", "status": "ok"}
