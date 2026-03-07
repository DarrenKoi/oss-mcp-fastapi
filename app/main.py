from fastapi import FastAPI

from app.common.ftp_proxy.router import router as ftp_proxy_router
from app.mcp.router import router as mcp_router
from app.oss.router import router as oss_router
from app.skewnono.router import router as skewnono_router

app = FastAPI(title="Internal MCP FastAPI Server")

for router in (oss_router, mcp_router, skewnono_router, ftp_proxy_router):
    app.include_router(router, prefix="/v1")


@app.get("/health")
def health():
    return {"status": "ok"}
