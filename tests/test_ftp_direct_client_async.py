import pytest

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient
from app.common.ftp_proxy.ftp_proxy_server import FTPProxyServer
from tests.ftp_fakes import FakeFTP, async_patch_connect


pytestmark = [pytest.mark.anyio, pytest.mark.unit, pytest.mark.home]


async def test_alist_files(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir"}),
                ("report.csv", {"type": "file", "size": "3"}),
            ]
        },
    )
    async_patch_connect(monkeypatch, FTPDirectClient, fake_ftp)

    response = await FTPDirectClient("fab-tool").alist_files_response("/recipes")

    assert response["strategy"] == "mlsd_path"
    assert [e["name"] for e in response["entries"]] == ["logs", "report.csv"]


async def test_alist_files_entries_only(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir"}),
            ]
        },
    )
    async_patch_connect(monkeypatch, FTPDirectClient, fake_ftp)

    entries = await FTPDirectClient("fab-tool").alist_files("/recipes")

    assert len(entries) == 1
    assert entries[0]["name"] == "logs"


async def test_adownload_and_aupload(monkeypatch, tmp_path):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        downloads={"/recipes/report.csv": b"fab-data"},
    )
    async_patch_connect(monkeypatch, FTPDirectClient, fake_ftp)
    client = FTPDirectClient("fab-tool")

    downloaded = await client.adownload(
        "/recipes/report.csv",
        str(tmp_path / "downloads" / "report.csv"),
    )

    upload_source = tmp_path / "upload.txt"
    upload_source.write_bytes(b"new-data")
    upload_result = await client.aupload(str(upload_source), "/recipes")

    assert downloaded.read_bytes() == b"fab-data"
    assert upload_result == {
        "status": "uploaded",
        "remote_path": "/recipes/upload.txt",
    }
    assert fake_ftp.uploads == [("STOR upload.txt", b"new-data")]


async def test_adownload_stream(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/"},
        downloads={"/data.bin": b"chunk1chunk2"},
    )
    async_patch_connect(monkeypatch, FTPDirectClient, fake_ftp)
    client = FTPDirectClient("fab-tool")

    chunks = []
    async for chunk in client.adownload_stream("/data.bin"):
        chunks.append(chunk)

    assert b"".join(chunks) == b"chunk1chunk2"


async def test_adownload_stream_closes_generator_on_early_exit(monkeypatch):
    closed = False

    def fake_download_stream(self, path):
        nonlocal closed
        assert path == "/data.bin"
        try:
            yield b"chunk-1"
            yield b"chunk-2"
        finally:
            closed = True

    monkeypatch.setattr(
        FTPDirectClient,
        "download_stream",
        fake_download_stream,
    )

    stream = FTPDirectClient("fab-tool").adownload_stream("/data.bin")

    assert await anext(stream) == b"chunk-1"
    await stream.aclose()

    assert closed is True


async def test_proxy_server_async_aliases(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir"}),
            ]
        },
    )
    async_patch_connect(monkeypatch, FTPProxyServer, fake_ftp)
    server = FTPProxyServer("fab-tool")

    entries = await server.alist_dir("/recipes")
    response = await server.alist_dir_response("/recipes")

    assert len(entries) == 1
    assert entries[0]["name"] == "logs"
    assert response["strategy"] == "mlsd_path"


async def test_proxy_server_aupload_with_fileobj(monkeypatch, tmp_path):
    fake_ftp = FakeFTP(directories={"/", "/recipes"})
    async_patch_connect(monkeypatch, FTPProxyServer, fake_ftp)
    server = FTPProxyServer("fab-tool")

    upload_source = tmp_path / "upload.txt"
    upload_source.write_bytes(b"async-data")

    with open(upload_source, "rb") as file_obj:
        result = await server.aupload("/recipes", "stream.txt", file_obj)

    assert result == "/recipes/stream.txt"
    assert fake_ftp.uploads == [("STOR stream.txt", b"async-data")]
