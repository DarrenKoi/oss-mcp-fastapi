import posixpath
import re
from contextlib import contextmanager, suppress
from datetime import datetime
from ftplib import FTP, all_errors
from typing import Any, BinaryIO, Generator


class FTPProxyServer:
    """Proxy server that connects to fab FTP servers and serves files to office users."""

    UNIX_LIST_PATTERN = re.compile(
        r"^(?P<permissions>[bcdlps-][rwxStTs-]{9})\s+"
        r"(?P<links>\d+)\s+"
        r"(?P<owner>\S+)\s+"
        r"(?P<group>\S+)\s+"
        r"(?P<size>\d+)\s+"
        r"(?P<month>[A-Za-z]{3})\s+"
        r"(?P<day>\d{1,2})\s+"
        r"(?P<time_or_year>\d{2}:\d{2}|\d{4})\s+"
        r"(?P<name>.+)$"
    )
    WINDOWS_LIST_PATTERN = re.compile(
        r"^(?P<date>\d{2}-\d{2}-\d{2,4})\s+"
        r"(?P<time>\d{1,2}:\d{2}(?:AM|PM))\s+"
        r"(?P<size_or_dir><DIR>|\d+)\s+"
        r"(?P<name>.+)$",
        re.IGNORECASE,
    )

    def __init__(self, host: str, port: int = 21, user: str = "anonymous", password: str = ""):
        self.host = host
        self.port = port
        self.user = user
        self.password = password

    @contextmanager
    def _connect(self) -> Generator[FTP, None, None]:
        ftp = FTP()
        ftp.connect(self.host, self.port)
        ftp.login(self.user, self.password)
        try:
            yield ftp
        finally:
            with suppress(all_errors):
                ftp.quit()

    def list_dir(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_dir_response(path)["entries"]

    def list_dir_response(self, path: str = "/") -> dict[str, Any]:
        normalized_path = self._normalize_path(path)
        attempts: list[dict[str, Any]] = []

        with self._connect() as ftp:
            strategies = (
                ("mlsd_path", self._list_via_mlsd_path),
                ("mlsd_cwd", self._list_via_mlsd_cwd),
                ("list_cwd", self._list_via_list_cwd),
                ("list_path", self._list_via_list_path),
                ("nlst_cwd", self._list_via_nlst_cwd),
                ("nlst_path", self._list_via_nlst_path),
            )

            for strategy_name, strategy in strategies:
                try:
                    entries = strategy(ftp, normalized_path)
                except Exception as exc:
                    attempts.append(
                        {
                            "strategy": strategy_name,
                            "status": "failed",
                            "error": str(exc),
                        }
                    )
                    continue

                attempts.append(
                    {
                        "strategy": strategy_name,
                        "status": "ok",
                        "entry_count": len(entries),
                    }
                )
                return {
                    "path": normalized_path,
                    "entries": entries,
                    "strategy": strategy_name,
                    "attempts": attempts,
                }

        formatted_attempts = ", ".join(
            f"{attempt['strategy']}: {attempt['error']}" for attempt in attempts if attempt["status"] == "failed"
        )
        raise RuntimeError(f"Unable to list remote directory '{normalized_path}': {formatted_attempts}")

    def _list_via_mlsd_path(self, ftp: FTP, path: str) -> list[dict[str, Any]]:
        return self._entries_from_mlsd(ftp.mlsd(path), source="mlsd")

    def _list_via_mlsd_cwd(self, ftp: FTP, path: str) -> list[dict[str, Any]]:
        with self._working_directory(ftp, path):
            return self._entries_from_mlsd(ftp.mlsd(), source="mlsd")

    def _list_via_list_path(self, ftp: FTP, path: str) -> list[dict[str, Any]]:
        lines: list[str] = []
        ftp.retrlines(f"LIST {path}", lines.append)
        return self._entries_from_list(lines)

    def _list_via_list_cwd(self, ftp: FTP, path: str) -> list[dict[str, Any]]:
        with self._working_directory(ftp, path):
            lines: list[str] = []
            ftp.retrlines("LIST", lines.append)
        return self._entries_from_list(lines)

    def _list_via_nlst_path(self, ftp: FTP, path: str) -> list[dict[str, Any]]:
        names = ftp.nlst(path)
        return self._entries_from_nlst(ftp, base_dir=path, names=names)

    def _list_via_nlst_cwd(self, ftp: FTP, path: str) -> list[dict[str, Any]]:
        with self._working_directory(ftp, path):
            base_dir = self._safe_pwd(ftp) or path
            names = ftp.nlst()
            return self._entries_from_nlst(ftp, base_dir=base_dir, names=names)

    def _entries_from_mlsd(self, rows, source: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for name, facts in rows:
            fact_type = str(facts.get("type", "")).lower()
            if name in {".", ".."} or fact_type in {"cdir", "pdir"}:
                continue
            entries.append(
                {
                    "name": name,
                    "permissions": facts.get("unix.mode") or facts.get("perm"),
                    "size": self._to_int(facts.get("size")),
                    "date": self._format_modify_timestamp(facts.get("modify")),
                    "is_dir": fact_type == "dir" if fact_type else None,
                    "source": source,
                    "facts": dict(facts),
                }
            )
        return entries

    def _entries_from_list(self, lines: list[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in lines:
            entry = self._parse_list_line(line)
            if entry is None or entry["name"] in {".", ".."}:
                continue
            entries.append(entry)
        return entries

    def _entries_from_nlst(self, ftp: FTP, base_dir: str, names: list[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for raw_name in names:
            display_name = self._display_name(raw_name)
            if not display_name or display_name in {".", ".."}:
                continue
            remote_path = self._join_remote_path(base_dir, raw_name)
            entries.append(self._describe_nlst_entry(ftp, remote_path, display_name))
        return entries

    def _describe_nlst_entry(self, ftp: FTP, remote_path: str, display_name: str) -> dict[str, Any]:
        facts = self._try_mlst(ftp, remote_path)
        if facts is not None:
            return {
                "name": display_name,
                "permissions": facts.get("unix.mode") or facts.get("perm"),
                "size": self._to_int(facts.get("size")),
                "date": self._format_modify_timestamp(facts.get("modify")),
                "is_dir": self._type_to_is_dir(facts.get("type")),
                "source": "nlst",
                "facts": facts,
            }

        if self._is_directory(ftp, remote_path):
            return {
                "name": display_name,
                "permissions": None,
                "size": None,
                "date": None,
                "is_dir": True,
                "source": "nlst",
            }

        size = self._try_size(ftp, remote_path)
        return {
            "name": display_name,
            "permissions": None,
            "size": size,
            "date": None,
            "is_dir": False if size is not None else None,
            "source": "nlst",
        }

    def _parse_list_line(self, line: str) -> dict[str, Any] | None:
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("total "):
            return None

        unix_match = self.UNIX_LIST_PATTERN.match(stripped)
        if unix_match:
            return {
                "name": unix_match.group("name"),
                "permissions": unix_match.group("permissions"),
                "size": int(unix_match.group("size")),
                "date": (
                    f"{unix_match.group('month')} "
                    f"{unix_match.group('day')} "
                    f"{unix_match.group('time_or_year')}"
                ),
                "is_dir": unix_match.group("permissions").startswith("d"),
                "source": "list",
            }

        windows_match = self.WINDOWS_LIST_PATTERN.match(stripped)
        if windows_match:
            size_or_dir = windows_match.group("size_or_dir")
            is_dir = size_or_dir.upper() == "<DIR>"
            return {
                "name": windows_match.group("name"),
                "permissions": None,
                "size": None if is_dir else int(size_or_dir),
                "date": f"{windows_match.group('date')} {windows_match.group('time')}",
                "is_dir": is_dir,
                "source": "list",
            }

        return {
            "name": stripped,
            "permissions": None,
            "size": None,
            "date": None,
            "is_dir": None,
            "source": "list",
            "raw": stripped,
        }

    @contextmanager
    def _working_directory(self, ftp: FTP, path: str) -> Generator[None, None, None]:
        original = self._safe_pwd(ftp)
        ftp.cwd(path)
        try:
            yield
        finally:
            if original is not None:
                with suppress(all_errors):
                    ftp.cwd(original)

    def _safe_pwd(self, ftp: FTP) -> str | None:
        with suppress(all_errors):
            return ftp.pwd()
        return None

    def _try_mlst(self, ftp: FTP, remote_path: str) -> dict[str, str] | None:
        try:
            response = ftp.sendcmd(f"MLST {remote_path}")
        except all_errors:
            return None
        return self._parse_mlst_response(response)

    def _try_size(self, ftp: FTP, remote_path: str) -> int | None:
        try:
            return ftp.size(remote_path)
        except all_errors:
            return None

    def _is_directory(self, ftp: FTP, remote_path: str) -> bool:
        original = self._safe_pwd(ftp)
        try:
            ftp.cwd(remote_path)
        except all_errors:
            return False
        finally:
            if original is not None:
                with suppress(all_errors):
                    ftp.cwd(original)
        return True

    def _parse_mlst_response(self, response: str) -> dict[str, str]:
        for line in response.splitlines():
            stripped = line.strip()
            if "=" not in stripped or ";" not in stripped:
                continue
            facts_blob = stripped.split(" ", maxsplit=1)[0]
            facts: dict[str, str] = {}
            for fact in facts_blob.split(";"):
                if "=" not in fact:
                    continue
                key, value = fact.split("=", maxsplit=1)
                facts[key.lower()] = value
            if facts:
                return facts
        return {}

    def _normalize_path(self, path: str) -> str:
        normalized = (path or "/").strip().replace("\\", "/")
        return normalized or "/"

    def _join_remote_path(self, base_dir: str, raw_name: str) -> str:
        normalized_name = str(raw_name).replace("\\", "/")
        if normalized_name.startswith("/") or re.match(r"^[A-Za-z]:/", normalized_name):
            return normalized_name
        if base_dir in {"", "/"}:
            return f"/{normalized_name.lstrip('/')}"
        return posixpath.join(base_dir.rstrip("/"), normalized_name)

    def _display_name(self, raw_name: str) -> str:
        normalized_name = str(raw_name).strip().replace("\\", "/").rstrip("/")
        if "/" not in normalized_name:
            return normalized_name
        return posixpath.basename(normalized_name)

    def _format_modify_timestamp(self, value: str | None) -> str | None:
        if not value:
            return None
        for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M%S.%f"):
            with suppress(ValueError):
                return datetime.strptime(value, fmt).strftime("%Y-%m-%d %H:%M:%S")
        return value

    def _to_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _type_to_is_dir(self, value: str | None) -> bool | None:
        if value is None:
            return None
        normalized = str(value).lower()
        if normalized in {"dir", "cdir", "pdir"}:
            return True
        if normalized == "file":
            return False
        return None

    def download_stream(self, path: str) -> Generator[bytes, None, None]:
        with self._connect() as ftp:
            ftp.voidcmd("TYPE I")
            with ftp.transfercmd(f"RETR {path}") as conn:
                while True:
                    chunk = conn.recv(8192)
                    if not chunk:
                        break
                    yield chunk
            ftp.voidresp()

    def upload(self, remote_dir: str, filename: str, file: BinaryIO) -> str:
        remote_path = f"{remote_dir.rstrip('/')}/{filename}"
        with self._connect() as ftp:
            ftp.cwd(remote_dir)
            ftp.storbinary(f"STOR {remote_path}", file)
        return remote_path
