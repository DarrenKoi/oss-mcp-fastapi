from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Callable

import httpx


class FTPBatchClient:
    """HTTP SDK for triggering batch downloads across multiple FTP hosts."""

    def __init__(
        self,
        proxy_url: str,
        *,
        port: int = 21,
        user: str = "anonymous",
        password: str = "",
        timeout: int | None = None,
        encoding: str | None = None,
        http_client: httpx.Client | None = None,
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.encoding = encoding
        self.http_client = http_client

    @contextmanager
    def _http_session(self):
        if self.http_client is not None:
            yield self.http_client
            return
        with httpx.Client() as client:
            yield client

    def _build_body(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        max_workers: int,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "hosts": hosts,
            "remote_path": remote_path,
            "base_dir": base_dir,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "max_workers": max_workers,
        }
        if self.timeout is not None:
            body["timeout"] = self.timeout
        if self.encoding:
            body["encoding"] = self.encoding
        return body

    def batch_download(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        *,
        max_workers: int = 4,
    ) -> dict[str, Any]:
        body = self._build_body(hosts, remote_path, base_dir, max_workers)
        with self._http_session() as client:
            resp = client.post(
                f"{self.proxy_url}/ftp-proxy/v1/batch-download",
                json=body,
                timeout=httpx.Timeout(timeout=None),
            )
        resp.raise_for_status()
        return resp.json()

    def batch_download_stream(
        self,
        hosts: list[str],
        remote_path: str,
        base_dir: str,
        *,
        max_workers: int = 4,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        body = self._build_body(hosts, remote_path, base_dir, max_workers)
        summary: dict[str, Any] = {}
        with self._http_session() as client:
            with client.stream(
                "POST",
                f"{self.proxy_url}/ftp-proxy/v1/batch-download/stream",
                json=body,
                timeout=httpx.Timeout(timeout=None),
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        if "host" in data and on_progress:
                            on_progress(data)
                        elif "total" in data:
                            summary = data
        return summary
