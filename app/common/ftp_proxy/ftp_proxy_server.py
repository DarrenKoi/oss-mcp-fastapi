import asyncio
import time
from typing import Any, BinaryIO, Generator, overload

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient
from app.common.ftp_proxy.ftp_logger import get_ftp_proxy_logger

logger = get_ftp_proxy_logger("server").getChild("proxy_server")


class FTPProxyServer(FTPDirectClient):
    """직접 FTP 클라이언트를 FastAPI 라우터에서 쓰기 쉽게 감싼 어댑터."""

    def list_dir(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_dir_response(path)["entries"]

    def list_dir_response(self, path: str = "/") -> dict[str, Any]:
        start = time.monotonic()
        normalized_path = self._normalize_path(path)
        logger.info(
            "Starting FTP list target=%s path=%s",
            self._log_target(),
            normalized_path,
        )
        try:
            response = super().list_files_response(normalized_path)
        except Exception:
            logger.exception(
                "Failed FTP list target=%s path=%s elapsed_seconds=%.3f",
                self._log_target(),
                normalized_path,
                time.monotonic() - start,
            )
            raise

        logger.info(
            "Completed FTP list target=%s path=%s entries=%d strategy=%s "
            "elapsed_seconds=%.3f",
            self._log_target(),
            response["path"],
            len(response["entries"]),
            response.get("strategy"),
            time.monotonic() - start,
        )
        return response

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
        return (await self.alist_dir_response(path))["entries"]

    async def alist_dir_response(self, path: str = "/") -> dict[str, Any]:
        return await asyncio.to_thread(self.list_dir_response, path)

    def download_stream(self, path: str) -> Generator[bytes, None, None]:
        start = time.monotonic()
        normalized_path = self._normalize_path(path)
        transferred_bytes = 0
        logger.info(
            "Starting FTP download target=%s remote_path=%s",
            self._log_target(),
            normalized_path,
        )
        try:
            for chunk in super().download_stream(normalized_path):
                transferred_bytes += len(chunk)
                yield chunk
        except Exception:
            logger.exception(
                "Failed FTP download target=%s remote_path=%s "
                "transferred_bytes=%d elapsed_seconds=%.3f",
                self._log_target(),
                normalized_path,
                transferred_bytes,
                time.monotonic() - start,
            )
            raise

        logger.info(
            "Completed FTP download target=%s remote_path=%s "
            "transferred_bytes=%d elapsed_seconds=%.3f",
            self._log_target(),
            normalized_path,
            transferred_bytes,
            time.monotonic() - start,
        )

    def _upload_fileobj(
        self, remote_dir: str, filename: str, file_obj: BinaryIO
    ) -> str:
        start = time.monotonic()
        normalized_dir = self._normalize_path(remote_dir)
        file_size = self._safe_file_size(file_obj)
        logger.info(
            "Starting FTP upload target=%s remote_dir=%s filename=%s "
            "file_size=%s",
            self._log_target(),
            normalized_dir,
            filename,
            file_size,
        )
        try:
            remote_path = super()._upload_fileobj(normalized_dir, filename, file_obj)
        except Exception:
            logger.exception(
                "Failed FTP upload target=%s remote_dir=%s filename=%s "
                "file_size=%s elapsed_seconds=%.3f",
                self._log_target(),
                normalized_dir,
                filename,
                file_size,
                time.monotonic() - start,
            )
            raise

        logger.info(
            "Completed FTP upload target=%s remote_path=%s filename=%s "
            "file_size=%s elapsed_seconds=%.3f",
            self._log_target(),
            remote_path,
            filename,
            file_size,
            time.monotonic() - start,
        )
        return remote_path

    async def aupload(
        self, arg1: str, arg2: str, file: BinaryIO | None = None
    ) -> dict[str, str] | str:
        if file is None:
            return await super().aupload(arg1, arg2)
        return await asyncio.to_thread(self._upload_fileobj, arg1, arg2, file)

    def _log_target(self) -> str:
        return f"{self.host}:{self.port}"

    @staticmethod
    def _safe_file_size(file_obj: BinaryIO) -> int | None:
        if not hasattr(file_obj, "tell") or not hasattr(file_obj, "seek"):
            return None
        try:
            original_position = file_obj.tell()
            file_obj.seek(0, 2)
            size = file_obj.tell()
            file_obj.seek(original_position)
            return size
        except (AttributeError, OSError, ValueError):
            return None
