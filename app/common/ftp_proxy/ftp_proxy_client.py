from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from app.common.ftp_proxy.ftp_client_base import FTPListResponseNormalizer


class _FTPProxyClientBase(FTPListResponseNormalizer):
    """프록시 클라이언트가 공통으로 쓰는 FTP 접속 설정."""

    def __init__(
        self,
        proxy_url: str,
        ftp_host: str,
        ftp_port: int = 21,
        ftp_user: str = "anonymous",
        ftp_password: str = "",
        *,
        ftp_timeout: int | None = None,
        ftp_encoding: str | None = None,
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.ftp_host = ftp_host
        self.ftp_port = ftp_port
        self.ftp_user = ftp_user
        self.ftp_password = ftp_password
        self.ftp_timeout = ftp_timeout
        self.ftp_encoding = ftp_encoding

    def _ftp_params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "host": self.ftp_host,
            "port": self.ftp_port,
            "user": self.ftp_user,
            "password": self.ftp_password,
        }
        if self.ftp_timeout is not None:
            params["timeout"] = self.ftp_timeout
        if self.ftp_encoding:
            params["encoding"] = self.ftp_encoding
        return params


class FTPProxyClient(_FTPProxyClientBase):
    """HTTP 프록시를 통해 FTP 작업을 수행하는 비동기 SDK."""

    def __init__(
        self,
        proxy_url: str,
        ftp_host: str,
        ftp_port: int = 21,
        ftp_user: str = "anonymous",
        ftp_password: str = "",
        *,
        ftp_timeout: int | None = None,
        ftp_encoding: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        super().__init__(
            proxy_url,
            ftp_host,
            ftp_port,
            ftp_user,
            ftp_password,
            ftp_timeout=ftp_timeout,
            ftp_encoding=ftp_encoding,
        )
        self.http_client = http_client

    @asynccontextmanager
    async def _http_session(self):
        if self.http_client is not None:
            yield self.http_client
            return
        async with httpx.AsyncClient() as client:
            yield client

    async def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        return (await self.list_files_response(path))["entries"]

    async def list_files_response(self, path: str = "/") -> dict[str, Any]:
        params = {**self._ftp_params(), "path": path}
        async with self._http_session() as client:
            resp = await client.get(
                f"{self.proxy_url}/ftp-proxy/v1/list", params=params
            )
        resp.raise_for_status()
        # 서버 응답 포맷 차이를 감추고 항상 같은 목록 구조로 돌려준다.
        return self._normalize_list_response(resp.json(), path)

    async def download(self, remote_path: str, local_path: str) -> Path:
        params = {**self._ftp_params(), "path": remote_path}
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        async with self._http_session() as client:
            async with client.stream(
                "GET",
                f"{self.proxy_url}/ftp-proxy/v1/download",
                params=params,
            ) as resp:
                resp.raise_for_status()
                with open(local, "wb") as file_obj:
                    async for chunk in resp.aiter_bytes(chunk_size=8192):
                        file_obj.write(chunk)
        return local

    async def upload(self, local_path: str, remote_dir: str) -> dict[str, Any]:
        params = {**self._ftp_params(), "path": remote_dir}
        local = Path(local_path)
        with open(local, "rb") as file_obj:
            files = {"file": (local.name, file_obj)}
            async with self._http_session() as client:
                resp = await client.post(
                    f"{self.proxy_url}/ftp-proxy/v1/upload",
                    params=params,
                    files=files,
                )
        resp.raise_for_status()
        return resp.json()
