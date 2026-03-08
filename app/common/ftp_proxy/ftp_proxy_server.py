import asyncio
from typing import Any, BinaryIO, overload

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient


class FTPProxyServer(FTPDirectClient):
    """직접 FTP 클라이언트를 FastAPI 라우터에서 쓰기 쉽게 감싼 어댑터."""

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
        # 로컬 파일 경로 업로드와 업로드된 file object 업로드를
        # 같은 이름으로 제공하기 위해 인자 조합에 따라 분기한다.
        if file is None:
            return super().upload(arg1, arg2)
        return self._upload_fileobj(arg1, arg2, file)

    async def alist_dir(self, path: str = "/") -> list[dict[str, Any]]:
        return await self.alist_files(path)

    async def alist_dir_response(self, path: str = "/") -> dict[str, Any]:
        return await self.alist_files_response(path)

    async def aupload(
        self, arg1: str, arg2: str, file: BinaryIO | None = None
    ) -> dict[str, str] | str:
        if file is None:
            return await super().aupload(arg1, arg2)
        return await asyncio.to_thread(self._upload_fileobj, arg1, arg2, file)
