from contextlib import contextmanager
from ftplib import error_perm

from app.common.ftp_proxy.ftp_proxy_server import FTPProxyServer


class FakeFTP:
    def __init__(
        self,
        *,
        directories: set[str] | None = None,
        mlsd_entries=None,
        list_lines=None,
        nlst_entries=None,
        sizes: dict[str, int] | None = None,
        mlst_responses: dict[str, str] | None = None,
    ):
        self.current_dir = "/"
        self.directories = directories or {"/"}
        self.mlsd_entries = mlsd_entries
        self.list_lines = list_lines
        self.nlst_entries = nlst_entries
        self.sizes = sizes or {}
        self.mlst_responses = mlst_responses or {}
        self.commands: list[tuple[str, str | None]] = []

    def _resolve(self, path: str | None) -> str:
        if path in (None, "", "."):
            resolved = self.current_dir
        else:
            candidate = str(path).replace("\\", "/")
            if candidate.startswith("/"):
                resolved = candidate
            elif self.current_dir == "/":
                resolved = f"/{candidate}"
            else:
                resolved = f"{self.current_dir.rstrip('/')}/{candidate}"

        normalized = resolved.rstrip("/")
        return normalized or "/"

    def _lookup(self, value, path: str):
        if isinstance(value, Exception):
            raise value
        if isinstance(value, dict):
            resolved = self._resolve(path)
            selected = value.get(resolved, value.get(path))
            if isinstance(selected, Exception):
                raise selected
            return selected
        return value

    def pwd(self) -> str:
        self.commands.append(("pwd", None))
        return self.current_dir

    def cwd(self, path: str) -> str:
        self.commands.append(("cwd", path))
        resolved = self._resolve(path)
        if resolved not in self.directories:
            raise error_perm("550 Not a directory")
        self.current_dir = resolved
        return "250 Directory changed"

    def mlsd(self, path: str | None = None):
        self.commands.append(("mlsd", path))
        entries = self._lookup(self.mlsd_entries, path or self.current_dir)
        if entries is None:
            raise error_perm("500 MLSD not supported")
        return iter(entries)

    def retrlines(self, command: str, callback):
        self.commands.append(("retrlines", command))
        path = command[4:].strip() if command.startswith("LIST") else ""
        lines = self._lookup(self.list_lines, path or self.current_dir)
        if lines is None:
            raise error_perm("500 LIST not supported")
        for line in lines:
            callback(line)
        return "226 Transfer complete"

    def nlst(self, path: str | None = None):
        self.commands.append(("nlst", path))
        entries = self._lookup(self.nlst_entries, path or self.current_dir)
        if entries is None:
            raise error_perm("500 NLST not supported")
        return list(entries)

    def size(self, path: str) -> int:
        self.commands.append(("size", path))
        resolved = self._resolve(path)
        if resolved not in self.sizes:
            raise error_perm("550 SIZE not available")
        return self.sizes[resolved]

    def sendcmd(self, command: str) -> str:
        self.commands.append(("sendcmd", command))
        if not command.startswith("MLST "):
            raise error_perm("500 Unsupported command")
        target = self._resolve(command[5:].strip())
        if target not in self.mlst_responses:
            raise error_perm("500 MLST not supported")
        return self.mlst_responses[target]


def patch_connect(monkeypatch, fake_ftp: FakeFTP) -> None:
    @contextmanager
    def fake_connect(self):
        yield fake_ftp

    monkeypatch.setattr(FTPProxyServer, "_connect", fake_connect)


def test_list_dir_uses_mlsd_when_available(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries={
            "/recipes": [
                ("logs", {"type": "dir", "modify": "20260308143000"}),
                ("report.csv", {"type": "file", "size": "128", "modify": "20260308143100"}),
            ]
        },
    )
    patch_connect(monkeypatch, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert set(by_name) == {"logs", "report.csv"}
    assert by_name["logs"]["is_dir"] is True
    assert by_name["report.csv"]["is_dir"] is False
    assert by_name["report.csv"]["size"] == 128
    assert any(command[0] == "mlsd" for command in fake_ftp.commands)


def test_list_dir_falls_back_to_unix_list_parsing(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes"},
        mlsd_entries=error_perm("500 MLSD not supported"),
        list_lines={
            "/recipes": [
                "drwxr-xr-x 2 owner group 4096 Mar 08 14:30 fab_logs",
                "-rw-r--r-- 1 owner group 128 Mar 08 14:31 process report.txt",
            ]
        },
    )
    patch_connect(monkeypatch, fake_ftp)

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
    patch_connect(monkeypatch, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["Recipe Data"]["is_dir"] is True
    assert by_name["wafer map.csv"]["is_dir"] is False
    assert by_name["wafer map.csv"]["size"] == 512


def test_list_dir_falls_back_to_nlst_with_best_effort_metadata(monkeypatch):
    fake_ftp = FakeFTP(
        directories={"/", "/recipes", "/recipes/docs"},
        mlsd_entries=error_perm("500 MLSD not supported"),
        list_lines=error_perm("500 LIST not supported"),
        nlst_entries={"/recipes": ["docs", "report.csv"]},
        sizes={"/recipes/report.csv": 321},
        mlst_responses={
            "/recipes/docs": "250-Listing\n type=dir;modify=20260308150000; /recipes/docs\n250 End",
            "/recipes/report.csv": "250-Listing\n type=file;size=321;modify=20260308150100; /recipes/report.csv\n250 End",
        },
    )
    patch_connect(monkeypatch, fake_ftp)

    entries = FTPProxyServer("fab-tool").list_dir("/recipes")
    by_name = {entry["name"]: entry for entry in entries}

    assert by_name["docs"]["is_dir"] is True
    assert by_name["report.csv"]["is_dir"] is False
    assert by_name["report.csv"]["size"] == 321
    assert any(command[0] == "nlst" for command in fake_ftp.commands)
