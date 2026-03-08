from ftplib import error_perm

from app.common.ftp_proxy.ftp_proxy_server import FTPProxyServer
from tests.ftp_fakes import FakeFTP, patch_connect


def test_list_dir_uses_mlsd_when_available(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir", "modify": "20260308143000"}),
                (
                    "report.csv",
                    {
                        "type": "file",
                        "size": "128",
                        "modify": "20260308143100",
                    },
                ),
            ]
        },
    )
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert set(by_name) == {"logs", "report.csv"}
    assert by_name["logs"]["is_dir"] is True
    assert by_name["report.csv"]["is_dir"] is False
    assert by_name["report.csv"]["size"] == 128
    assert any(command[0] == "mlsd" for command in fake_ftp.commands)


def test_list_dir_tries_cwd_mlsd_after_path_mlsd_failure(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries=lambda raw_path, _resolved: (
            error_perm("500 MLSD path form not supported")
            if raw_path
            else [
                ("logs", {"type": "dir"}),
                ("report.csv", {"type": "file", "size": "7"}),
            ]
        ),
    )
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)

    response = FTPProxyServer("fab-tool").list_dir_response("/recipes")

    assert response["strategy"] == "mlsd_cwd"
    assert [entry["name"] for entry in response["entries"]] == [
        "logs",
        "report.csv",
    ]
    assert response["attempts"][0]["strategy"] == "mlsd_path"
    assert response["attempts"][0]["status"] == "failed"
    assert response["attempts"][1]["strategy"] == "mlsd_cwd"
    assert response["attempts"][1]["status"] == "ok"


def test_list_dir_falls_back_to_unix_list_parsing(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries=error_perm("500 MLSD not supported"),
        list_lines={
            "/recipes": [
                "drwxr-xr-x 2 owner group 4096 Mar 08 14:30 fab_logs",
                (
                    "-rw-r--r-- 1 owner group 128 Mar 08 14:31 "
                    "process report.txt"
                ),
            ]
        },
    )
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["fab_logs"]["is_dir"] is True
    assert by_name["fab_logs"]["permissions"].startswith("d")
    assert by_name["process report.txt"]["is_dir"] is False
    assert by_name["process report.txt"]["size"] == 128


def test_list_dir_falls_back_to_windows_list_parsing(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries=error_perm("500 MLSD not supported"),
        list_lines={
            "/recipes": [
                "03-08-26  02:30PM       <DIR>          Recipe Data",
                "03-08-26  02:31PM                  512 wafer map.csv",
            ]
        },
    )
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["Recipe Data"]["is_dir"] is True
    assert by_name["wafer map.csv"]["is_dir"] is False
    assert by_name["wafer map.csv"]["size"] == 512


def test_list_dir_falls_back_to_nlst_with_best_effort_metadata(
    monkeypatch,
):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes", "/recipes/docs"},
        mlsd_entries=error_perm("500 MLSD not supported"),
        list_lines=error_perm("500 LIST not supported"),
        nlst_entries={"/recipes": ["docs", "report.csv"]},
        sizes={"/recipes/report.csv": 321},
        mlst_responses={
            "/recipes/docs": (
                "250-Listing\n"
                " type=dir;modify=20260308150000; /recipes/docs\n"
                "250 End"
            ),
            "/recipes/report.csv": (
                "250-Listing\n"
                " type=file;size=321;modify=20260308150100; "
                "/recipes/report.csv\n"
                "250 End"
            ),
        },
    )
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["docs"]["is_dir"] is True
    assert by_name["report.csv"]["is_dir"] is False
    assert by_name["report.csv"]["size"] == 321
    assert any(command[0] == "nlst" for command in fake_ftp.commands)


def test_list_dir_falls_back_when_mlst_response_has_no_parseable_facts(
    monkeypatch,
):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes", "/recipes/docs"},
        mlsd_entries=error_perm("500 MLSD not supported"),
        list_lines=error_perm("500 LIST not supported"),
        nlst_entries={"/recipes": ["docs", "report.csv"]},
        sizes={"/recipes/report.csv": 99},
        mlst_responses={
            "/recipes/docs": "250 docs listing without facts",
            "/recipes/report.csv": "250 report listing without facts",
        },
    )
    patch_connect(monkeypatch, FTPProxyServer, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["docs"]["is_dir"] is True
    assert by_name["report.csv"]["is_dir"] is False
    assert by_name["report.csv"]["size"] == 99
