from fastapi import APIRouter

from app.mcp.v1 import router as v1_router

router = APIRouter(prefix="/mcp", tags=["MCP"])

router.include_router(v1_router)
