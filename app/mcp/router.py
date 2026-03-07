from fastapi import APIRouter

router = APIRouter(prefix="/mcp", tags=["MCP"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"service": "mcp", "status": "ok"}
