import os

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.common.ftp_proxy.ftp_proxy_server import FTPProxyServer

router = APIRouter(prefix="/ftp-proxy/v1", tags=["FTP Proxy"])


@router.get("/list")
def ftp_list(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    timeout: int = Query(30, ge=1),
    encoding: str | None = Query(None),
    path: str = Query("/"),
):
    try:
        server = FTPProxyServer(
            host,
            port,
            user,
            password,
            timeout=timeout,
            encoding=encoding,
        )
        return server.list_dir_response(path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")


@router.get("/download")
def ftp_download(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    timeout: int = Query(30, ge=1),
    encoding: str | None = Query(None),
    path: str = Query(...),
):
    filename = os.path.basename(path)
    server = FTPProxyServer(
        host,
        port,
        user,
        password,
        timeout=timeout,
        encoding=encoding,
    )

    return StreamingResponse(
        server.download_stream(path),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload")
def ftp_upload(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    timeout: int = Query(30, ge=1),
    encoding: str | None = Query(None),
    path: str = Query(..., description="Remote directory path to upload to"),
    file: UploadFile = File(...),
):
    try:
        server = FTPProxyServer(
            host,
            port,
            user,
            password,
            timeout=timeout,
            encoding=encoding,
        )
        remote_path = server.upload(path, file.filename, file.file)
        return {"status": "uploaded", "remote_path": remote_path}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")
