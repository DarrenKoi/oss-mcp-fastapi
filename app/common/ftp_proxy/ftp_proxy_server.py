from typing import Any, BinaryIO, overload

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient


class FTPProxyServer(FTPDirectClient):
    """Proxy adapter that exposes direct FTP operations over HTTP."""

    def list_dir(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_files(path)

    def list_dir_response(self, path: str = "/") -> dict[str, Any]:
        return self.list_files_response(path)

    @overload
    def upload(self, local_path: str, remote_dir: str) -> dict[str, str]:
        ...

    @overload
    def upload(
        self, remote_dir: str, filename: str, file: BinaryIO
    ) -> str:
        ...

    def upload(
        self, arg1: str, arg2: str, file: BinaryIO | None = None
    ) -> dict[str, str] | str:
        if file is None:
            return super().upload(arg1, arg2)
        return self._upload_fileobj(arg1, arg2, file)
