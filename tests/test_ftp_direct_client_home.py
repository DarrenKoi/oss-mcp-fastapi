import logging

from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient
from app.common.ftp_proxy.ftp_proxy_server import FTPProxyServer
from tests.ftp_fakes import FakeFTP, patch_connect


def test_direct_client_lists_files(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir"}),
                ("report.csv", {"type": "file", "size": "3"}),
            ]
        },
    )
    patch_connect(monkeypatch, FTPDirectClient, fake_ftp)

    response = FTPDirectClient("fab-tool").list_files_response("/recipes")

    assert response["strategy"] == "mlsd_path"
    assert [entry["name"] for entry in response["entries"]] == [
        "logs",
        "report.csv",
    ]


def test_direct_client_downloads_and_uploads(monkeypatch, tmp_path):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        downloads={"/recipes/report.csv": b"fab-data"},
    )
    patch_connect(monkeypatch, FTPDirectClient, fake_ftp)
    client = FTPDirectClient("fab-tool")

    downloaded = client.download(
        "/recipes/report.csv",
        str(tmp_path / "downloads" / "report.csv"),
    )

    upload_source = tmp_path / "upload.txt"
    upload_source.write_bytes(b"new-data")
    upload_result = client.upload(str(upload_source), "/recipes")

    assert downloaded.read_bytes() == b"fab-data"
    assert upload_result == {
        "status": "uploaded",
        "remote_path": "/recipes/upload.txt",
    }
    assert fake_ftp.uploads == [("STOR upload.txt", b"new-data")]


def test_direct_client_normalizes_windows_style_remote_paths(
    monkeypatch, tmp_path
):
    fake_ftp = FakeFTP(
        directories={"/", "C:/recipes"},
        downloads={"C:/recipes/report.csv": b"fab-data"},
    )
    patch_connect(monkeypatch, FTPDirectClient, fake_ftp)
    client = FTPDirectClient("fab-tool")

    downloaded = client.download(
        r"C:\recipes\report.csv",
        str(tmp_path / "downloads" / "report.csv"),
    )

    upload_source = tmp_path / "upload.txt"
    upload_source.write_bytes(b"new-data")
    upload_result = client.upload(str(upload_source), r"C:\recipes")

    assert downloaded.read_bytes() == b"fab-data"
    assert upload_result == {
        "status": "uploaded",
        "remote_path": "C:/recipes/upload.txt",
    }
    assert ("transfercmd", "RETR C:/recipes/report.csv") in fake_ftp.commands
    assert ("cwd", "C:/recipes") in fake_ftp.commands
    assert fake_ftp.uploads == [("STOR upload.txt", b"new-data")]


def test_direct_client_allows_encoding_override(monkeypatch):
    class RecordingFTP:
        instance = None

        def __init__(self, timeout=None):
            self.timeout = timeout
            self.encoding = "utf-8"
            self.connected = None
            self.logged_in = None
            self.quit_called = False
            RecordingFTP.instance = self

        def connect(self, host, port, timeout=None):
            self.connected = (host, port, timeout)

        def login(self, user, password):
            self.logged_in = (user, password)

        def quit(self):
            self.quit_called = True

    monkeypatch.setattr(
        "app.common.ftp_proxy.ftp_direct_client.FTP",
        RecordingFTP,
    )

    client = FTPDirectClient(
        "fab-tool",
        user="operator",
        password="secret",
        timeout=17,
        encoding="cp949",
    )

    with client._connect() as ftp:
        assert ftp.encoding == "cp949"

    assert RecordingFTP.instance.connected == ("fab-tool", 21, 17)
    assert RecordingFTP.instance.logged_in == ("operator", "secret")
    assert RecordingFTP.instance.quit_called is True


def test_proxy_server_upload_supports_base_and_stream_signatures(
    monkeypatch, tmp_path, caplog
):
    fake_ftp = FakeFTP(directories={"/", "/recipes"})
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)
    server = FTPProxyServer("fab-tool")
    caplog.set_level(logging.INFO)

    upload_source = tmp_path / "upload.txt"
    upload_source.write_bytes(b"new-data")

    base_result = server.upload(str(upload_source), "/recipes")

    with open(upload_source, "rb") as file_obj:
        stream_result = server.upload("/recipes", "stream.txt", file_obj)

    assert base_result == {
        "status": "uploaded",
        "remote_path": "/recipes/upload.txt",
    }
    assert stream_result == "/recipes/stream.txt"
    assert fake_ftp.uploads == [
        ("STOR upload.txt", b"new-data"),
        ("STOR stream.txt", b"new-data"),
    ]
    assert (
        "Starting FTP upload target=fab-tool:21 remote_dir=/recipes "
        "filename=upload.txt file_size=8"
    ) in caplog.text
    assert (
        "Completed FTP upload target=fab-tool:21 "
        "remote_path=/recipes/stream.txt filename=stream.txt file_size=8"
    ) in caplog.text
