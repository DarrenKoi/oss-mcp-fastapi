from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient


@dataclass
class ToolDownloadResult:
    host: str
    status: Literal["success", "failed"]
    local_path: str | None = None
    error: str | None = None
    elapsed_seconds: float = 0.0


@dataclass
class BatchDownloadResult:
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[ToolDownloadResult] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class FTPBatchDownloader:
    """Downloads the same file(s) from multiple FTP hosts concurrently.

    Organises output as ``{base_dir}/{host}/{filename}`` so files from
    different tools never overwrite each other.
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
        """Download a single file from one host. Runs in a worker thread."""
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
