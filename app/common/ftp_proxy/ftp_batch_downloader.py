from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient


@dataclass
class ToolDownloadResult:
    """개별 호스트 한 대의 다운로드 결과."""

    host: str
    status: Literal["success", "failed"]
    local_path: str | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class BatchDownloadResult:
    """배치 다운로드 전체 집계 결과."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[ToolDownloadResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class FTPBatchDownloader:
    """여러 FTP 호스트에서 같은 경로를 동시에 내려받는다.

    저장 경로를 ``{base_dir}/{host}/{filename}`` 형태로 고정해서
    장비별 파일이 서로 덮어쓰지 않게 한다.
    """

    MAX_WORKERS_CAP = 8

    def __init__(
        self,
        *,
        port: int = 21,
        user: str = "anonymous",
        password: str = "",
        timeout: int = 30,
        encoding: str | None = None,
    ):
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.encoding = encoding

    def _download_one(
        self, host: str, remote_path: str, base_dir: str
    ) -> ToolDownloadResult:
        """워커 스레드 하나가 담당하는 단일 호스트 다운로드 작업."""
        start = time.monotonic()
        try:
            client = FTPDirectClient(
                host,
                self.port,
                self.user,
                self.password,
                timeout=self.timeout,
                encoding=self.encoding,
            )
            local_dir = Path(base_dir) / host
            filename = Path(remote_path).name
            local_path = str(local_dir / filename)
            client.download(remote_path, local_path)
            return ToolDownloadResult(
                host=host,
                status="success",
                local_path=local_path,
                elapsed_seconds=time.monotonic() - start,
            )
        except Exception as exc:
            return ToolDownloadResult(
                host=host,
                status="failed",
                error=str(exc),
                elapsed_seconds=time.monotonic() - start,
            )

    def batch_download(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        *,
        max_workers: int = 4,
        on_complete: Callable[[ToolDownloadResult], None] | None = None,
    ) -> BatchDownloadResult:
        effective_workers = min(max(max_workers, 1), self.MAX_WORKERS_CAP)
        result = BatchDownloadResult(total=len(hosts))
        start = time.monotonic()

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            # 완료 순서대로 결과를 수집해서, 느린 호스트가 있어도
            # 먼저 끝난 작업의 상태를 바로 상위 호출자에 전달할 수 있다.
            futures = {
                executor.submit(
                    self._download_one, host, remote_path, base_dir
                ): host
                for host in hosts
            }
            for future in as_completed(futures):
                tool_result = future.result()
                result.results.append(tool_result)
                if tool_result.status == "success":
                    result.succeeded += 1
                else:
                    result.failed += 1
                if on_complete:
                    on_complete(tool_result)

        result.elapsed_seconds = time.monotonic() - start
        return result
