import logging

import pytest
import httpx

from app.common.ftp_proxy.ftp_batch_client import FTPBatchClient


pytestmark = [pytest.mark.anyio, pytest.mark.unit, pytest.mark.home]


class FakeAsyncResponse:
    def __init__(self, payload=None, *, lines=None):
        self.payload = payload
        self.lines = list(lines or [])

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class FakeAsyncHTTPClient:
    def __init__(self, *, post_payload=None, stream_lines=None):
        self.post_payload = post_payload
        self.stream_lines = list(stream_lines or [])
        self.calls: list[tuple[str, tuple, dict]] = []

    async def post(self, url, **kwargs):
        self.calls.append(("post", (url,), kwargs))
        return FakeAsyncResponse(payload=self.post_payload)

    def stream(self, method, url, **kwargs):
        self.calls.append(("stream", (method, url), kwargs))
        return FakeAsyncResponse(lines=self.stream_lines)


async def test_batch_download_posts_request_body_and_returns_json():
    payload = {"total": 2, "succeeded": 2, "failed": 0}
    http_client = FakeAsyncHTTPClient(post_payload=payload)
    client = FTPBatchClient(
        "http://proxy.internal",
        timeout=12,
        encoding="cp949",
        http_client=http_client,
    )

    response = await client.batch_download(
        ["fab-1", "fab-2"],
        "/recipes/report.csv",
        "/tmp/downloads",
        max_workers=6,
    )

    assert response == payload
    assert http_client.calls[0][:2] == (
        "post",
        ("http://proxy.internal/ftp-proxy/v1/batch-download",),
    )
    assert http_client.calls[0][2]["json"] == {
        "hosts": ["fab-1", "fab-2"],
        "remote_path": "/recipes/report.csv",
        "base_dir": "/tmp/downloads",
        "port": 21,
        "user": "anonymous",
        "password": "",
        "max_workers": 6,
        "timeout": 12,
        "encoding": "cp949",
    }
    timeout = http_client.calls[0][2]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect is None
    assert timeout.read is None
    assert timeout.write is None
    assert timeout.pool is None


async def test_batch_download_stream_reports_progress_and_returns_summary():
    progress_events: list[dict] = []
    http_client = FakeAsyncHTTPClient(
        stream_lines=[
            "event: progress",
            'data: {"host": "fab-1", "status": "success"}',
            "",
            'data: {"host": "fab-2", "status": "failed"}',
            'data: {"total": 2, "succeeded": 1, "failed": 1}',
        ]
    )
    client = FTPBatchClient("http://proxy.internal", http_client=http_client)
    summary = await client.batch_download_stream(
        ["fab-1", "fab-2"],
        "/recipes/report.csv",
        "/tmp/downloads",
        on_progress=progress_events.append,
    )

    assert progress_events == [
        {"host": "fab-1", "status": "success"},
        {"host": "fab-2", "status": "failed"},
    ]
    assert summary == {"total": 2, "succeeded": 1, "failed": 1}
    assert http_client.calls[0][:2] == (
        "stream",
        ("POST", "http://proxy.internal/ftp-proxy/v1/batch-download/stream"),
    )
    assert http_client.calls[0][2]["json"] == {
        "hosts": ["fab-1", "fab-2"],
        "remote_path": "/recipes/report.csv",
        "base_dir": "/tmp/downloads",
        "port": 21,
        "user": "anonymous",
        "password": "",
        "max_workers": 4,
    }
    timeout = http_client.calls[0][2]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect is None
    assert timeout.read is None
    assert timeout.write is None
    assert timeout.pool is None


async def test_batch_download_stream_logs_progress_and_summary(caplog):
    progress_events: list[dict] = []
    http_client = FakeAsyncHTTPClient(
        stream_lines=[
            'data: {"host": "fab-1", "status": "success"}',
            'data: {"host": "fab-2", "status": "failed", "error": "timeout"}',
            'data: {"total": 2, "succeeded": 1, "failed": 1}',
        ]
    )
    client = FTPBatchClient("http://proxy.internal", http_client=http_client)
    caplog.set_level(logging.INFO)

    summary = await client.batch_download_stream(
        ["fab-1", "fab-2"],
        "/recipes/report.csv",
        "/tmp/downloads",
        on_progress=progress_events.append,
    )

    assert progress_events == [
        {"host": "fab-1", "status": "success"},
        {"host": "fab-2", "status": "failed", "error": "timeout"},
    ]
    assert summary == {"total": 2, "succeeded": 1, "failed": 1}
    assert http_client.calls[0][:2] == (
        "stream",
        ("POST", "http://proxy.internal/ftp-proxy/v1/batch-download/stream"),
    )
    assert http_client.calls[0][2]["json"] == {
        "hosts": ["fab-1", "fab-2"],
        "remote_path": "/recipes/report.csv",
        "base_dir": "/tmp/downloads",
        "port": 21,
        "user": "anonymous",
        "password": "",
        "max_workers": 4,
    }
    timeout = http_client.calls[0][2]["timeout"]
    assert isinstance(timeout, httpx.Timeout)
    assert timeout.connect is None
    assert timeout.read is None
    assert timeout.write is None
    assert timeout.pool is None
    assert (
        "Starting proxy batch download stream proxy_url=http://proxy.internal "
        "hosts=2 remote_path=/recipes/report.csv"
    ) in caplog.text
    assert "Proxy batch download progress host=fab-1 status=success" in caplog.text
    assert "Proxy batch download progress host=fab-2 status=failed" in caplog.text
    assert (
        "Completed proxy batch download stream proxy_url=http://proxy.internal "
        "hosts=2 remote_path=/recipes/report.csv succeeded=1 failed=1 "
        "progress_events=2"
    ) in caplog.text


async def test_batch_download_stream_awaits_async_progress_callback():
    progress_events: list[dict] = []
    http_client = FakeAsyncHTTPClient(
        stream_lines=[
            'data: {"host": "fab-1", "status": "success"}',
            'data: {"total": 1, "succeeded": 1, "failed": 0}',
        ]
    )
    client = FTPBatchClient("http://proxy.internal", http_client=http_client)

    async def on_progress(event: dict) -> None:
        progress_events.append(event)

    summary = await client.batch_download_stream(
        ["fab-1"],
        "/recipes/report.csv",
        "/tmp/downloads",
        on_progress=on_progress,
    )

    assert progress_events == [{"host": "fab-1", "status": "success"}]
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_batch_client_normalizes_windows_style_remote_paths():
    payload = {"total": 1, "succeeded": 1, "failed": 0}
    http_client = FakeAsyncHTTPClient(post_payload=payload)
    client = FTPBatchClient("http://proxy.internal", http_client=http_client)

    response = await client.batch_download(
        ["fab-1"],
        r"C:\recipes\report.csv",
        "/tmp/downloads",
    )

    assert response == payload
    assert http_client.calls[0][2]["json"]["remote_path"] == (
        "C:/recipes/report.csv"
    )


async def test_batch_client_uses_env_default_proxy_url(monkeypatch):
    payload = {"total": 1, "succeeded": 1, "failed": 0}
    http_client = FakeAsyncHTTPClient(post_payload=payload)
    monkeypatch.setenv("FTP_PROXY_URL", "https://proxy.from.env/")
    client = FTPBatchClient(http_client=http_client)

    response = await client.batch_download(
        ["fab-1"],
        "/recipes/report.csv",
        "/tmp/downloads",
    )

    assert response == payload
    assert client.proxy_url == "https://proxy.from.env"
    assert http_client.calls[0][:2] == (
        "post",
        ("https://proxy.from.env/ftp-proxy/v1/batch-download",),
    )
