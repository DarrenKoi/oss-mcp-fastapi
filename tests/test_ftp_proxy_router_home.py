import pytest
from fastapi.testclient import TestClient

from app.main import app


pytestmark = [pytest.mark.api, pytest.mark.home]


def test_list_route_uses_async_server(monkeypatch):
    async def fake_alist_dir_response(self, path):
        assert path == "/recipes"
        return {"path": path, "entries": [{"name": "report.csv"}]}

    monkeypatch.setattr(
        "app.common.ftp_proxy.router_v1.FTPProxyServer.alist_dir_response",
        fake_alist_dir_response,
    )

    client = TestClient(app)
    response = client.get(
        "/ftp-proxy/v1/list",
        params={"host": "fab-tool", "path": "/recipes"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "path": "/recipes",
        "entries": [{"name": "report.csv"}],
    }


def test_download_route_streams_async_chunks(monkeypatch):
    async def fake_adownload_stream(self, path):
        assert path == "/recipes/report.csv"
        yield b"fab-"
        yield b"data"

    monkeypatch.setattr(
        "app.common.ftp_proxy.router_v1.FTPProxyServer.adownload_stream",
        fake_adownload_stream,
    )

    client = TestClient(app)
    response = client.get(
        "/ftp-proxy/v1/download",
        params={"host": "fab-tool", "path": "/recipes/report.csv"},
    )

    assert response.status_code == 200
    assert response.content == b"fab-data"
    assert response.headers["content-disposition"] == (
        'attachment; filename="report.csv"'
    )


def test_download_route_returns_502_when_stream_fails_before_first_chunk(
    monkeypatch,
):
    async def fake_adownload_stream(self, path):
        raise RuntimeError("fab offline")
        yield b"unused"

    monkeypatch.setattr(
        "app.common.ftp_proxy.router_v1.FTPProxyServer.adownload_stream",
        fake_adownload_stream,
    )

    client = TestClient(app)
    response = client.get(
        "/ftp-proxy/v1/download",
        params={"host": "fab-tool", "path": "/recipes/report.csv"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "FTP error: fab offline"}


def test_upload_route_uses_async_server(monkeypatch):
    async def fake_aupload(self, remote_dir, filename, file_obj):
        assert remote_dir == "/recipes"
        assert filename == "data.txt"
        assert file_obj.read() == b"fab-data"
        return "/recipes/data.txt"

    monkeypatch.setattr(
        "app.common.ftp_proxy.router_v1.FTPProxyServer.aupload",
        fake_aupload,
    )

    client = TestClient(app)
    response = client.post(
        "/ftp-proxy/v1/upload?host=fab-tool&path=/recipes",
        files={"file": ("data.txt", b"fab-data", "text/plain")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "uploaded",
        "remote_path": "/recipes/data.txt",
    }
