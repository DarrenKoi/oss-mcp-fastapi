import pytest

from app.common.ftp_proxy.ftp_proxy_client import FTPProxyClient


pytestmark = [pytest.mark.unit, pytest.mark.home]


class FakeResponse:
    def __init__(self, payload=None, *, chunks=None):
        self.payload = payload
        self.chunks = list(chunks or [])

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_bytes(self, chunk_size=8192):
        yield from self.chunks


class FakeHTTPClient:
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

    def get(self, url, **kwargs):
        self.calls.append(("get", (url,), kwargs))
        return FakeResponse(self.get_payload)

    def post(self, url, **kwargs):
        self.calls.append(("post", (url,), kwargs))
        return FakeResponse(self.post_payload)

    def stream(self, method, url, **kwargs):
        self.calls.append(("stream", (method, url), kwargs))
        return FakeResponse(chunks=self.stream_chunks)


def test_download_writes_streamed_bytes(tmp_path):
    http_client = FakeHTTPClient(stream_chunks=[b"fab-", b"data"])
    client = FTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        http_client=http_client,
    )

    downloaded = client.download(
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


def test_list_files_handles_server_metadata_response(monkeypatch):
    payload = {
        "path": "/recipes",
        "strategy": "list_cwd",
        "attempts": [{"strategy": "mlsd_path", "status": "failed"}],
        "entries": [
            {"name": "docs", "is_dir": True, "size": None, "source": "list"},
            {"name": "report.csv", "is_dir": False, "size": 128, "date": "2026-03-08 14:31:00"},
        ],
    }

    def fake_get(url, params):
        assert url.endswith("/ftp-proxy/v1/list")
        assert params["path"] == "/recipes"
        return FakeResponse(payload)

    monkeypatch.setattr(
        "app.common.ftp_proxy.ftp_proxy_client.httpx.Client.get",
        lambda self, url, **kwargs: fake_get(url, kwargs["params"]),
    )

    client = FTPProxyClient("http://proxy.internal", "fab-tool")
    response = client.list_files_response("/recipes")

    assert response["path"] == "/recipes"
    assert response["strategy"] == "list_cwd"
    assert response["entries"][0]["name"] == "docs"
    assert response["entries"][1]["size"] == 128


def test_list_files_normalizes_legacy_list_payload(monkeypatch):
    def fake_get(url, params):
        return FakeResponse(
            [
                {"filename": "logs", "type": "dir"},
                {"filename": "report.csv", "type": "file", "filesize": "321", "modified": "2026-03-08 14:31:00"},
            ]
        )

    monkeypatch.setattr(
        "app.common.ftp_proxy.ftp_proxy_client.httpx.Client.get",
        lambda self, url, **kwargs: fake_get(url, kwargs["params"]),
    )

    client = FTPProxyClient("http://proxy.internal", "fab-tool")
    entries = client.list_files("/recipes")

    assert entries[0]["name"] == "logs"
    assert entries[0]["is_dir"] is True
    assert entries[1]["name"] == "report.csv"
    assert entries[1]["size"] == 321
    assert entries[1]["is_dir"] is False


def test_list_files_normalizes_nested_payload_keys(monkeypatch):
    payload = {
        "data": {
            "files": [
                {"path": "/recipes/docs", "directory": "true"},
                {"pathname": "/recipes/report.csv", "length": "42", "kind": "file"},
            ]
        }
    }

    def fake_get(url, params):
        return FakeResponse(payload)

    monkeypatch.setattr(
        "app.common.ftp_proxy.ftp_proxy_client.httpx.Client.get",
        lambda self, url, **kwargs: fake_get(url, kwargs["params"]),
    )

    client = FTPProxyClient("http://proxy.internal", "fab-tool")
    response = client.list_files_response("/recipes")

    assert [entry["name"] for entry in response["entries"]] == ["docs", "report.csv"]
    assert response["entries"][0]["is_dir"] is True
    assert response["entries"][1]["size"] == 42
    assert response["entries"][1]["is_dir"] is False


def test_proxy_client_sends_optional_timeout_and_encoding(monkeypatch):
    captured = {}

    def fake_get(url, params):
        captured.update(params)
        return FakeResponse({"entries": []})

    monkeypatch.setattr(
        "app.common.ftp_proxy.ftp_proxy_client.httpx.Client.get",
        lambda self, url, **kwargs: fake_get(url, kwargs["params"]),
    )

    client = FTPProxyClient(
        "http://proxy.internal",
        "fab-tool",
        ftp_timeout=12,
        ftp_encoding="cp949",
    )
    response = client.list_files_response("/recipes")

    assert response["entries"] == []
    assert captured["timeout"] == 12
    assert captured["encoding"] == "cp949"
