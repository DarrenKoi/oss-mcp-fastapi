from pathlib import Path
from typing import Any

import httpx

from app.common.ftp_proxy.ftp_client_base import FTPListResponseNormalizer


class FTPProxyClient(FTPListResponseNormalizer):
    """HTTP SDK for office users to access the FTP proxy server."""

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

    def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_files_response(path)["entries"]

    def list_files_response(self, path: str = "/") -> dict[str, Any]:
        params = {**self._ftp_params(), "path": path}
        resp = httpx.get(f"{self.proxy_url}/ftp-proxy/v1/list", params=params)
        resp.raise_for_status()
        return self._normalize_list_response(resp.json(), path)

    def download(self, remote_path: str, local_path: str) -> Path:
        params = {**self._ftp_params(), "path": remote_path}
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "GET",
            f"{self.proxy_url}/ftp-proxy/v1/download",
            params=params,
        ) as resp:
            resp.raise_for_status()
            with open(local, "wb") as file_obj:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    file_obj.write(chunk)
        return local

    def upload(self, local_path: str, remote_dir: str) -> dict[str, Any]:
        params = {**self._ftp_params(), "path": remote_dir}
        local = Path(local_path)
        with open(local, "rb") as file_obj:
            files = {"file": (local.name, file_obj)}
            resp = httpx.post(
                f"{self.proxy_url}/ftp-proxy/v1/upload",
                params=params,
                files=files,
            )
        resp.raise_for_status()
        return resp.json()
