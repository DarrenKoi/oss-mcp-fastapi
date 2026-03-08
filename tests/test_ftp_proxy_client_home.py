from app.common.ftp_proxy.ftp_proxy_client import FTPProxyClient


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


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

    monkeypatch.setattr("app.common.ftp_proxy.ftp_proxy_client.httpx.get", fake_get)

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

    monkeypatch.setattr("app.common.ftp_proxy.ftp_proxy_client.httpx.get", fake_get)

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

    monkeypatch.setattr("app.common.ftp_proxy.ftp_proxy_client.httpx.get", fake_get)

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

    monkeypatch.setattr("app.common.ftp_proxy.ftp_proxy_client.httpx.get", fake_get)

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
