from fastapi import FastAPI

from app.common.ftp_proxy.router import router as ftp_proxy_router

app = FastAPI(title="Internal MCP FastAPI Server")

app.include_router(ftp_proxy_router)


@app.get("/health")
def health():
    return {"status": "ok"}
