import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

from app.common.ftp_proxy.ftp_client_base import FTPListResponseNormalizer
from app.common.ftp_proxy.ftp_logger import get_ftp_proxy_logger
from app.common.ftp_proxy.ftp_path import normalize_remote_path
from app.common.ftp_proxy.proxy_url import default_proxy_url

logger = get_ftp_proxy_logger("client").getChild("proxy_client")


class _FTPProxyClientBase(FTPListResponseNormalizer):
    """프록시 클라이언트가 공통으로 쓰는 FTP 접속 설정."""

    def __init__(
        self,
        ftp_host: str,
        ftp_port: int = 21,
        ftp_user: str = "anonymous",
        ftp_password: str = "",
        *,
        proxy_url: str | None = None,
        ftp_timeout: int | None = None,
        ftp_encoding: str | None = None,
    ):
        self.proxy_url = (
            proxy_url.rstrip("/") if proxy_url else default_proxy_url()
        )
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

    def _ftp_target(self) -> str:
        return f"{self.ftp_host}:{self.ftp_port}"


class FTPProxyClient(_FTPProxyClientBase):
    """HTTP 프록시를 통해 FTP 작업을 수행하는 비동기 SDK."""

    def __init__(
        self,
        proxy_url_or_ftp_host: str,
        ftp_host: str | None = None,
        ftp_port: int = 21,
        ftp_user: str = "anonymous",
        ftp_password: str = "",
        *,
        proxy_url: str | None = None,
        ftp_timeout: int | None = None,
        ftp_encoding: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ):
        # 기존 "proxy_url, ftp_host" 호출과
        # 새 "ftp_host" 단독 호출을 모두 허용한다.
        if ftp_host is None:
            ftp_host = proxy_url_or_ftp_host
        elif proxy_url is None:
            proxy_url = proxy_url_or_ftp_host

        super().__init__(
            ftp_host,
            ftp_port,
            ftp_user,
            ftp_password,
            proxy_url=proxy_url,
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
        start = time.monotonic()
        normalized_path = normalize_remote_path(path)
        params = {
            **self._ftp_params(),
            "path": normalized_path,
        }
        logger.info(
            "Starting proxy list proxy_url=%s target=%s path=%s",
            self.proxy_url,
            self._ftp_target(),
            normalized_path,
        )
        try:
            async with self._http_session() as client:
                resp = await client.get(
                    f"{self.proxy_url}/ftp-proxy/v1/list", params=params
                )
            resp.raise_for_status()
            # 서버 응답 포맷 차이를 감추고 항상 같은 목록 구조로 돌려준다.
            response = self._normalize_list_response(
                resp.json(), normalized_path
            )
        except Exception:
            logger.exception(
                "Failed proxy list proxy_url=%s target=%s path=%s "
                "elapsed_seconds=%.3f",
                self.proxy_url,
                self._ftp_target(),
                normalized_path,
                time.monotonic() - start,
            )
            raise

        logger.info(
            "Completed proxy list proxy_url=%s target=%s path=%s entries=%d "
            "strategy=%s elapsed_seconds=%.3f",
            self.proxy_url,
            self._ftp_target(),
            normalized_path,
            len(response["entries"]),
            response.get("strategy"),
            time.monotonic() - start,
        )
        return response

    async def download(self, remote_path: str, local_path: str) -> Path:
        start = time.monotonic()
        normalized_remote_path = normalize_remote_path(remote_path)
        params = {
            **self._ftp_params(),
            "path": normalized_remote_path,
        }
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        transferred_bytes = 0
        logger.info(
            "Starting proxy download proxy_url=%s target=%s remote_path=%s "
            "local_path=%s",
            self.proxy_url,
            self._ftp_target(),
            normalized_remote_path,
            local,
        )
        try:
            async with self._http_session() as client:
                async with client.stream(
                    "GET",
                    f"{self.proxy_url}/ftp-proxy/v1/download",
                    params=params,
                ) as resp:
                    resp.raise_for_status()
                    with open(local, "wb") as file_obj:
                        async for chunk in resp.aiter_bytes(chunk_size=8192):
                            transferred_bytes += len(chunk)
                            file_obj.write(chunk)
        except Exception:
            logger.exception(
                "Failed proxy download proxy_url=%s target=%s remote_path=%s "
                "local_path=%s transferred_bytes=%d elapsed_seconds=%.3f",
                self.proxy_url,
                self._ftp_target(),
                normalized_remote_path,
                local,
                transferred_bytes,
                time.monotonic() - start,
            )
            raise

        logger.info(
            "Completed proxy download proxy_url=%s target=%s remote_path=%s "
            "local_path=%s transferred_bytes=%d elapsed_seconds=%.3f",
            self.proxy_url,
            self._ftp_target(),
            normalized_remote_path,
            local,
            transferred_bytes,
            time.monotonic() - start,
        )
        return local

    async def upload(self, local_path: str, remote_dir: str) -> dict[str, Any]:
        start = time.monotonic()
        normalized_remote_dir = normalize_remote_path(remote_dir)
        params = {
            **self._ftp_params(),
            "path": normalized_remote_dir,
        }
        local = Path(local_path)
        file_size = local.stat().st_size
        logger.info(
            "Starting proxy upload proxy_url=%s target=%s local_path=%s "
            "remote_dir=%s file_size=%d",
            self.proxy_url,
            self._ftp_target(),
            local,
            normalized_remote_dir,
            file_size,
        )
        try:
            with open(local, "rb") as file_obj:
                files = {"file": (local.name, file_obj)}
                async with self._http_session() as client:
                    resp = await client.post(
                        f"{self.proxy_url}/ftp-proxy/v1/upload",
                        params=params,
                        files=files,
                    )
            resp.raise_for_status()
            response = resp.json()
        except Exception:
            logger.exception(
                "Failed proxy upload proxy_url=%s target=%s local_path=%s "
                "remote_dir=%s file_size=%d elapsed_seconds=%.3f",
                self.proxy_url,
                self._ftp_target(),
                local,
                normalized_remote_dir,
                file_size,
                time.monotonic() - start,
            )
            raise

        logger.info(
            "Completed proxy upload proxy_url=%s target=%s local_path=%s "
            "remote_path=%s file_size=%d elapsed_seconds=%.3f",
            self.proxy_url,
            self._ftp_target(),
            local,
            response.get("remote_path"),
            file_size,
            time.monotonic() - start,
        )
        return response
