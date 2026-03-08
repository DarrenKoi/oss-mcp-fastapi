import pytest

from app.common.ftp_proxy.ftp_direct_async_adapter import (
    DirectFTPAsyncAdapter,
)
from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient
from tests.ftp_fakes import FakeFTP, async_patch_connect


pytestmark = [pytest.mark.anyio, pytest.mark.unit, pytest.mark.home]


async def test_direct_async_adapter_matches_shared_async_surface(
    monkeypatch, tmp_path
):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir"}),
                ("report.csv", {"type": "file", "size": "8"}),
            ]
        },
        downloads={"/recipes/report.csv": b"fab-data"},
    )
    async_patch_connect(monkeypatch, FTPDirectClient, fake_ftp)
    client = DirectFTPAsyncAdapter(
        "fab-tool",
        ftp_timeout=12,
        ftp_encoding="cp949",
    )

    response = await client.list_files_response("/recipes")
    entries = await client.list_files("/recipes")
    downloaded = await client.download(
        "/recipes/report.csv",
        str(tmp_path / "downloads" / "report.csv"),
    )

    upload_source = tmp_path / "upload.txt"
    upload_source.write_bytes(b"new-data")
    upload_result = await client.upload(str(upload_source), "/recipes")

    assert response["strategy"] == "mlsd_path"
    assert [entry["name"] for entry in entries] == ["logs", "report.csv"]
    assert downloaded.read_bytes() == b"fab-data"
    assert upload_result == {
        "status": "uploaded",
        "remote_path": "/recipes/upload.txt",
    }
    assert client.direct_client.timeout == 12
    assert client.direct_client.encoding == "cp949"
    assert fake_ftp.uploads == [("STOR upload.txt", b"new-data")]
