from typing import Any, BinaryIO

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient


class FTPProxyServer(FTPDirectClient):
    """Proxy adapter that exposes direct FTP operations over HTTP."""

    def list_dir(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_files(path)

    def list_dir_response(self, path: str = "/") -> dict[str, Any]:
        return self.list_files_response(path)

    def upload(
        self, remote_dir: str, filename: str, file: BinaryIO
    ) -> str:
        return self._upload_fileobj(remote_dir, filename, file)
