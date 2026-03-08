from __future__ import annotations

import inspect
import json
from contextlib import asynccontextmanager
from typing import Any, Callable

import httpx

from app.common.ftp_proxy.ftp_path import normalize_remote_path


class FTPBatchClient:
    """여러 FTP 호스트 대상 배치 다운로드 API를 호출하는 클라이언트."""

    def __init__(
        self,
        proxy_url: str,
        *,
        port: int = 21,
        user: str = "anonymous",
        password: str = "",
        timeout: int | None = None,
        encoding: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.encoding = encoding
        self.http_client = http_client

    @asynccontextmanager
    async def _http_session(self):
        if self.http_client is not None:
            yield self.http_client
            return
        async with httpx.AsyncClient() as client:
            yield client

    def _build_body(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        max_workers: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "hosts": hosts,
            "remote_path": normalize_remote_path(remote_path),
            "base_dir": base_dir,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "max_workers": max_workers,
        }
        if self.timeout is not None:
            body["timeout"] = self.timeout
        if self.encoding:
            body["encoding"] = self.encoding
        return body

    async def batch_download(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        *,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        body = self._build_body(hosts, remote_path, base_dir, max_workers)
        async with self._http_session() as client:
            resp = await client.post(
                f"{self.proxy_url}/ftp-proxy/v1/batch-download",
                json=body,
                timeout=httpx.Timeout(timeout=None),
            )
        resp.raise_for_status()
        return resp.json()

    async def batch_download_stream(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        *,
        max_workers: int = 4,
        on_progress: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        body = self._build_body(hosts, remote_path, base_dir, max_workers)
        summary: dict[str, Any] = {}
        async with self._http_session() as client:
            async with client.stream(
                "POST",
                f"{self.proxy_url}/ftp-proxy/v1/batch-download/stream",
                json=body,
                timeout=httpx.Timeout(timeout=None),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    # SSE는 event/data 줄 단위로 오므로 data 줄만 골라
                    # 진행 상황과 최종 요약을 각각 해석한다.
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "host" in data and on_progress:
                            callback_result = on_progress(data)
                            if inspect.isawaitable(callback_result):
                                await callback_result
                        elif "total" in data:
                            summary = data
        return summary
