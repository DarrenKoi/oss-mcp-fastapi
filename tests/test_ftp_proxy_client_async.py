import pytest

from app.common.ftp_proxy.ftp_proxy_client import AsyncFTPProxyClient


pytestmark = [pytest.mark.anyio, pytest.mark.unit, pytest.mark.home]


class FakeAsyncResponse:
    def __init__(self, payload=None, *, chunks=None):
        self.payload = payload
        self.chunks = list(chunks or [])

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def aiter_bytes(self, chunk_size=8192):
        for chunk in self.chunks:
            yield chunk


class FakeAsyncHTTPClient:
    def __init__(
        self,
        *,
        get_payload=None,
        post_payload=None,
        stream_chunks=None,
    ):
        self.get_payload = get_payload
        self.post_payload = post_payload
        self.stream_chunks = list(stream_chunks or [])
        self.calls: list[tuple[str, tuple, dict]] = []

    async def get(self, url, **kwargs):
        self.calls.append(("get", (url,), kwargs))
        return FakeAsyncResponse(self.get_payload)

    async def post(self, url, **kwargs):
        self.calls.append(("post", (url,), kwargs))
        return FakeAsyncResponse(self.post_payload)

    def stream(self, method, url, **kwargs):
        self.calls.append(("stream", (method, url), kwargs))
        return FakeAsyncResponse(chunks=self.stream_chunks)


async def test_async_list_files_response():
    payload = {
        "path": "/recipes",
        "strategy": "list_cwd",
        "attempts": [{"strategy": "mlsd_path", "status": "failed"}],
        "entries": [
            {"name": "docs", "is_dir": True, "size": None, "source": "list"},
            {"name": "report.csv", "is_dir": False, "size": 128},
        ],
    }
    http_client = FakeAsyncHTTPClient(get_payload=payload)
    client = AsyncFTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        http_client=http_client,
    )
    response = await client.list_files_response("/recipes")

    assert response["path"] == "/recipes"
    assert response["strategy"] == "list_cwd"
    assert response["entries"][0]["name"] == "docs"
    assert response["entries"][1]["size"] == 128
    assert http_client.calls == [
        (
            "get",
            ("http://proxy.internal/ftp-proxy/v1/list",),
            {
                "params": {
                    "host": "fab-tool",
                    "port": 21,
                    "user": "anonymous",
                    "password": "",
                    "path": "/recipes",
                }
            },
        )
    ]


async def test_async_list_files():
    payload = {
        "entries": [
            {"name": "logs", "is_dir": True},
        ],
    }
    client = AsyncFTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        http_client=FakeAsyncHTTPClient(get_payload=payload),
    )
    entries = await client.list_files("/recipes")

    assert len(entries) == 1
    assert entries[0]["name"] == "logs"


async def test_async_download(tmp_path):
    http_client = FakeAsyncHTTPClient(stream_chunks=[b"fab-", b"data"])
    client = AsyncFTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        http_client=http_client,
    )

    downloaded = await client.download(
        "/recipes/report.csv",
        str(tmp_path / "downloads" / "report.csv"),
    )

    assert downloaded.read_bytes() == b"fab-data"
    assert http_client.calls == [
        (
            "stream",
            ("GET", "http://proxy.internal/ftp-proxy/v1/download"),
            {
                "params": {
                    "host": "fab-tool",
                    "port": 21,
                    "user": "anonymous",
                    "password": "",
                    "path": "/recipes/report.csv",
                }
            },
        )
    ]


async def test_async_upload(tmp_path):
    upload_response = {"status": "uploaded", "remote_path": "/recipes/data.txt"}
    http_client = FakeAsyncHTTPClient(post_payload=upload_response)

    upload_file = tmp_path / "data.txt"
    upload_file.write_bytes(b"test-data")

    client = AsyncFTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        http_client=http_client,
    )
    result = await client.upload(str(upload_file), "/recipes")

    assert result == upload_response
    files = http_client.calls[0][2]["files"]
    assert http_client.calls[0][0] == "post"
    assert http_client.calls[0][1] == (
        "http://proxy.internal/ftp-proxy/v1/upload",
    )
    assert http_client.calls[0][2]["params"]["path"] == "/recipes"
    assert files["file"][0] == "data.txt"


async def test_async_client_sends_optional_timeout_and_encoding():
    http_client = FakeAsyncHTTPClient(get_payload={"entries": []})
    client = AsyncFTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        ftp_timeout=12,
        ftp_encoding="cp949",
        http_client=http_client,
    )
    response = await client.list_files_response("/recipes")

    assert response["entries"] == []
    params = http_client.calls[0][2]["params"]
    assert params["timeout"] == 12
    assert params["encoding"] == "cp949"
