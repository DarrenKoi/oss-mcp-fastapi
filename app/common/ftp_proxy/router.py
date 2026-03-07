import os

from fastapi import APIRouter, Query, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse

from app.common.ftp_proxy.ftp_client import ftp_connection, list_dir, download_stream, upload_file

router = APIRouter(prefix="/ftp-proxy", tags=["FTP Proxy"])


@router.get("/list")
def ftp_list(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    path: str = Query("/"),
):
    try:
        with ftp_connection(host, port, user, password) as ftp:
            entries = list_dir(ftp, path)
        return {"path": path, "entries": entries}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")


@router.get("/download")
def ftp_download(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    path: str = Query(...),
):
    filename = os.path.basename(path)

    def stream():
        with ftp_connection(host, port, user, password) as ftp:
            yield from download_stream(ftp, path)

    return StreamingResponse(
        stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/upload")
def ftp_upload(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    path: str = Query(..., description="Remote directory path to upload to"),
    file: UploadFile = File(...),
):
    remote_path = f"{path.rstrip('/')}/{file.filename}"
    try:
        with ftp_connection(host, port, user, password) as ftp:
            ftp.cwd(path)
            upload_file(ftp, remote_path, file.file)
        return {"status": "uploaded", "remote_path": remote_path}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")
