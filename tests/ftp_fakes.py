from contextlib import asynccontextmanager, contextmanager
from ftplib import error_perm


class FakeTransferSocket:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def recv(self, size: int) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        chunk = self.payload[self.offset : self.offset + size]
        self.offset += size
        return chunk


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
        downloads: dict[str, bytes] | None = None,
    ):
        self.current_dir = "/"
        self.directories = directories or {"/"}
        self.mlsd_entries = mlsd_entries
        self.list_lines = list_lines
        self.nlst_entries = nlst_entries
        self.sizes = sizes or {}
        self.mlst_responses = mlst_responses or {}
        self.downloads = downloads or {}
        self.commands: list[tuple[str, str | None]] = []
        self.uploads: list[tuple[str, bytes]] = []

    def _resolve(self, path: str | None) -> str:
        if path in (None, "", "."):
            resolved = self.current_dir
        else:
            candidate = str(path).replace("\\", "/")
            if candidate.startswith("/") or (
                len(candidate) >= 3
                and candidate[0].isalpha()
                and candidate[1:3] == ":/"
            ):
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
        if callable(value):
            selected = value(path, self._resolve(path))
            if isinstance(selected, Exception):
                raise selected
            return selected
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
        if callable(self.mlsd_entries):
            resolved = self._resolve(path or self.current_dir)
            entries = self.mlsd_entries(path, resolved)
            if isinstance(entries, Exception):
                raise entries
        else:
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
        if command == "TYPE I":
            return "200 Type set to I"
        if not command.startswith("MLST "):
            raise error_perm("500 Unsupported command")
        target = self._resolve(command[5:].strip())
        if target not in self.mlst_responses:
            raise error_perm("500 MLST not supported")
        return self.mlst_responses[target]

    def voidcmd(self, command: str) -> str:
        self.commands.append(("voidcmd", command))
        return self.sendcmd(command)

    def transfercmd(self, command: str):
        self.commands.append(("transfercmd", command))
        if not command.startswith("RETR "):
            raise error_perm("500 Unsupported transfer")
        target = self._resolve(command[5:].strip())
        payload = self.downloads.get(target)
        if payload is None:
            raise error_perm("550 File unavailable")
        return FakeTransferSocket(payload)

    def voidresp(self) -> str:
        self.commands.append(("voidresp", None))
        return "226 Transfer complete"

    def storbinary(self, command: str, file_obj) -> str:
        self.commands.append(("storbinary", command))
        self.uploads.append((command, file_obj.read()))
        return "226 Transfer complete"


def patch_connect(monkeypatch, cls, fake_ftp: FakeFTP) -> None:
    @contextmanager
    def fake_connect(self):
        yield fake_ftp

    monkeypatch.setattr(cls, "_connect", fake_connect)


def patch_connect_multi(
    monkeypatch, cls, fakes_by_host: dict[str, FakeFTP]
) -> None:
    @contextmanager
    def fake_connect(self):
        yield fakes_by_host[self.host]

    monkeypatch.setattr(cls, "_connect", fake_connect)


def async_patch_connect(monkeypatch, cls, fake_ftp: FakeFTP) -> None:
    @contextmanager
    def fake_connect(self):
        yield fake_ftp

    @asynccontextmanager
    async def fake_aconnect(self):
        yield fake_ftp

    monkeypatch.setattr(cls, "_connect", fake_connect)
    monkeypatch.setattr(cls, "_aconnect", fake_aconnect)
