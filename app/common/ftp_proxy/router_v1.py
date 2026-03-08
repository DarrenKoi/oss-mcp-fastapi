import json
import os
import queue
import threading

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.common.ftp_proxy.ftp_batch_downloader import FTPBatchDownloader
from app.common.ftp_proxy.ftp_proxy_server import FTPProxyServer

router = APIRouter(prefix="/ftp-proxy/v1", tags=["FTP Proxy"])


async def _prime_stream(stream):
    first_chunk = await anext(stream, None)

    async def body():
        try:
            if first_chunk is not None:
                yield first_chunk
            async for chunk in stream:
                yield chunk
        finally:
            await stream.aclose()

    return body()


@router.get("/list")
async def ftp_list(
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
        return await server.alist_dir_response(path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")


@router.get("/download")
async def ftp_download(
    host: str = Query(...),
    port: int = Query(21),
    user: str = Query("anonymous"),
    password: str = Query(""),
    timeout: int = Query(30, ge=1),
    encoding: str | None = Query(None),
    path: str = Query(...),
):
    filename = os.path.basename(path.rstrip("/")) or "download"

    try:
        server = FTPProxyServer(
            host,
            port,
            user,
            password,
            timeout=timeout,
            encoding=encoding,
        )
        stream = await _prime_stream(server.adownload_stream(path))
        return StreamingResponse(
            stream,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")


@router.post("/upload")
async def ftp_upload(
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
        remote_path = await server.aupload(path, file.filename, file.file)
        return {"status": "uploaded", "remote_path": remote_path}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"FTP error: {e}")


class BatchDownloadRequest(BaseModel):
    hosts: list[str] = Field(..., min_length=1)
    remote_path: str
    base_dir: str
    port: int = 21
    user: str = "anonymous"
    password: str = ""
    timeout: int = Field(30, ge=1)
    encoding: str | None = None
    max_workers: int = Field(4, ge=1, le=8)


def _make_downloader(req: BatchDownloadRequest) -> FTPBatchDownloader:
    return FTPBatchDownloader(
        port=req.port,
        user=req.user,
        password=req.password,
        timeout=req.timeout,
        encoding=req.encoding,
    )


def _format_tool_result(r) -> dict:
    return {
        "host": r.host,
        "status": r.status,
        "local_path": r.local_path,
        "error": r.error,
        "elapsed_seconds": round(r.elapsed_seconds, 2),
    }


@router.post("/batch-download")
def ftp_batch_download(request: BatchDownloadRequest):
    downloader = _make_downloader(request)
    result = downloader.batch_download(
        hosts=request.hosts,
        remote_path=request.remote_path,
        base_dir=request.base_dir,
        max_workers=request.max_workers,
    )
    return {
        "total": result.total,
        "succeeded": result.succeeded,
        "failed": result.failed,
        "elapsed_seconds": round(result.elapsed_seconds, 2),
        "results": [_format_tool_result(r) for r in result.results],
    }


@router.post("/batch-download/stream")
def ftp_batch_download_stream(request: BatchDownloadRequest):
    downloader = _make_downloader(request)

    def event_stream():
        q: queue.Queue = queue.Queue()

        def on_complete(tool_result):
            q.put(tool_result)

        result_holder: list = []

        def run_batch():
            result = downloader.batch_download(
                hosts=request.hosts,
                remote_path=request.remote_path,
                base_dir=request.base_dir,
                max_workers=request.max_workers,
                on_complete=on_complete,
            )
            result_holder.append(result)
            q.put(None)

        thread = threading.Thread(target=run_batch, daemon=True)
        thread.start()

        while True:
            item = q.get()
            if item is None:
                break
            data = json.dumps(_format_tool_result(item))
            yield f"event: progress\ndata: {data}\n\n"

        thread.join()
        result = result_holder[0]
        summary = json.dumps(
            {
                "total": result.total,
                "succeeded": result.succeeded,
                "failed": result.failed,
                "elapsed_seconds": round(result.elapsed_seconds, 2),
            }
        )
        yield f"event: done\ndata: {summary}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
