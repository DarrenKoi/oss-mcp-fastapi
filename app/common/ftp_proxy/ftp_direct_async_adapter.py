from pathlib import Path
from typing import Any

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient


class DirectFTPAsyncAdapter:
    """FTPDirectClient를 FTPProxyClient와 같은 async 표면으로 감싼다."""

    def __init__(
        self,
        ftp_host: str,
        ftp_port: int = 21,
        ftp_user: str = "anonymous",
        ftp_password: str = "",
        *,
        ftp_timeout: int | None = None,
        ftp_encoding: str | None = None,
    ):
        timeout = (
            ftp_timeout
            if ftp_timeout is not None
            else FTPDirectClient.DEFAULT_TIMEOUT
        )
        self.direct_client = FTPDirectClient(
            ftp_host,
            ftp_port,
            ftp_user,
            ftp_password,
            timeout=timeout,
            encoding=ftp_encoding,
        )

    async def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        return await self.direct_client.alist_files(path)

    async def list_files_response(self, path: str = "/") -> dict[str, Any]:
        return await self.direct_client.alist_files_response(path)

    async def download(self, remote_path: str, local_path: str) -> Path:
        return await self.direct_client.adownload(remote_path, local_path)

    async def upload(
        self, local_path: str, remote_dir: str
    ) -> dict[str, str]:
        return await self.direct_client.aupload(local_path, remote_dir)
