import posixpath
import re
from contextlib import contextmanager, suppress
from datetime import datetime
from ftplib import FTP, all_errors
from pathlib import Path
from typing import Any, BinaryIO, Generator


class FTPDirectClient:
    """Direct FTP client for cloud-side access to fab tools."""

    UNIX_LIST_PATTERN = re.compile(
        r"^(?P<permissions>[bcdlps-][rwxStTs-]{9}[+.@]?)\s+"
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
        r"^(?P<date>\d{2}[-/]\d{2}[-/]\d{2,4})\s+"
        r"(?P<time>\d{1,2}:\d{2}\s?(?:AM|PM))\s+"
        r"(?P<size_or_dir><DIR>|\d+)\s+"
        r"(?P<name>.+)$",
        re.IGNORECASE,
    )

    DEFAULT_TIMEOUT = 30

    def __init__(
        self,
        host: str,
        port: int = 21,
        user: str = "anonymous",
        password: str = "",
        *,
        timeout: int = DEFAULT_TIMEOUT,
        encoding: str | None = None,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self.encoding = encoding

    @contextmanager
    def _connect(self) -> Generator[FTP, None, None]:
        ftp = FTP(timeout=self.timeout)
        if self.encoding:
            ftp.encoding = self.encoding
        ftp.connect(self.host, self.port, timeout=self.timeout)
        ftp.login(self.user, self.password)
        try:
            yield ftp
        finally:
            with suppress(all_errors):
                ftp.quit()

    def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_files_response(path)["entries"]

    def list_files_response(self, path: str = "/") -> dict[str, Any]:
        normalized_path = self._normalize_path(path)
        attempts: list[dict[str, Any]] = []
        first_empty: dict[str, Any] | None = None

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

                if entries:
                    return {
                        "path": normalized_path,
                        "entries": entries,
                        "strategy": strategy_name,
                        "attempts": attempts,
                    }

                if first_empty is None:
                    first_empty = {
                        "path": normalized_path,
                        "entries": [],
                        "strategy": strategy_name,
                    }

        if first_empty is not None:
            first_empty["attempts"] = attempts
            return first_empty

        formatted_attempts = ", ".join(
            f"{attempt['strategy']}: {attempt['error']}"
            for attempt in attempts
            if attempt["status"] == "failed"
        )
        raise RuntimeError(
            f"Unable to list remote directory '{normalized_path}': "
            f"{formatted_attempts}"
        )

    def _list_via_mlsd_path(
        self, ftp: FTP, path: str
    ) -> list[dict[str, Any]]:
        return self._entries_from_mlsd(ftp.mlsd(path), source="mlsd")

    def _list_via_mlsd_cwd(
        self, ftp: FTP, path: str
    ) -> list[dict[str, Any]]:
        with self._working_directory(ftp, path):
            return self._entries_from_mlsd(ftp.mlsd(), source="mlsd")

    def _list_via_list_path(
        self, ftp: FTP, path: str
    ) -> list[dict[str, Any]]:
        lines: list[str] = []
        ftp.retrlines(f"LIST {path}", lines.append)
        return self._entries_from_list(lines)

    def _list_via_list_cwd(
        self, ftp: FTP, path: str
    ) -> list[dict[str, Any]]:
        with self._working_directory(ftp, path):
            lines: list[str] = []
            ftp.retrlines("LIST", lines.append)
        return self._entries_from_list(lines)

    def _list_via_nlst_path(
        self, ftp: FTP, path: str
    ) -> list[dict[str, Any]]:
        names = ftp.nlst(path)
        return self._entries_from_nlst(ftp, base_dir=path, names=names)

    def _list_via_nlst_cwd(
        self, ftp: FTP, path: str
    ) -> list[dict[str, Any]]:
        with self._working_directory(ftp, path):
            base_dir = self._safe_pwd(ftp) or path
            names = ftp.nlst()
            return self._entries_from_nlst(
                ftp, base_dir=base_dir, names=names
            )

    def _entries_from_mlsd(self, rows, source: str) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for name, facts in rows:
            fact_type = str(facts.get("type", "")).lower()
            if name in {".", ".."} or fact_type in {"cdir", "pdir"}:
                continue
            entries.append(
                {
                    "name": name,
                    "permissions": (
                        facts.get("unix.mode") or facts.get("perm")
                    ),
                    "size": self._to_int(facts.get("size")),
                    "date": self._format_modify_timestamp(
                        facts.get("modify")
                    ),
                    "is_dir": fact_type == "dir" if fact_type else None,
                    "source": source,
                    "facts": dict(facts),
                }
            )
        return entries

    def _entries_from_list(
        self, lines: list[str]
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for line in lines:
            entry = self._parse_list_line(line)
            if entry is None or entry["name"] in {".", ".."}:
                continue
            entries.append(entry)
        return entries

    def _entries_from_nlst(
        self, ftp: FTP, base_dir: str, names: list[str]
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        mlst_available = True
        for raw_name in names:
            display_name = self._display_name(raw_name)
            if not display_name or display_name in {".", ".."}:
                continue
            remote_path = self._join_remote_path(base_dir, raw_name)
            entry, mlst_available = self._describe_nlst_entry(
                ftp,
                remote_path,
                display_name,
                try_mlst=mlst_available,
            )
            entries.append(entry)
        return entries

    def _describe_nlst_entry(
        self,
        ftp: FTP,
        remote_path: str,
        display_name: str,
        *,
        try_mlst: bool = True,
    ) -> tuple[dict[str, Any], bool]:
        if try_mlst:
            facts, mlst_available = self._try_mlst(ftp, remote_path)
            if facts:
                return {
                    "name": display_name,
                    "permissions": (
                        facts.get("unix.mode") or facts.get("perm")
                    ),
                    "size": self._to_int(facts.get("size")),
                    "date": self._format_modify_timestamp(
                        facts.get("modify")
                    ),
                    "is_dir": self._type_to_is_dir(facts.get("type")),
                    "source": "nlst",
                    "facts": facts,
                }, mlst_available
            try_mlst = mlst_available

        if self._is_directory(ftp, remote_path):
            return {
                "name": display_name,
                "permissions": None,
                "size": None,
                "date": None,
                "is_dir": True,
                "source": "nlst",
            }, try_mlst

        size = self._try_size(ftp, remote_path)
        return {
            "name": display_name,
            "permissions": None,
            "size": size,
            "date": None,
            "is_dir": False if size is not None else None,
            "source": "nlst",
        }, try_mlst

    def _parse_list_line(self, line: str) -> dict[str, Any] | None:
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("total "):
            return None

        unix_match = self.UNIX_LIST_PATTERN.match(stripped)
        if unix_match:
            name = unix_match.group("name")
            link_target = None
            permissions = unix_match.group("permissions")
            if permissions.startswith("l") and " -> " in name:
                name, link_target = name.rsplit(" -> ", 1)
            entry: dict[str, Any] = {
                "name": name,
                "permissions": permissions,
                "size": int(unix_match.group("size")),
                "date": (
                    f"{unix_match.group('month')} "
                    f"{unix_match.group('day')} "
                    f"{unix_match.group('time_or_year')}"
                ),
                "is_dir": permissions.startswith("d"),
                "source": "list",
            }
            if link_target is not None:
                entry["link_target"] = link_target
            return entry

        windows_match = self.WINDOWS_LIST_PATTERN.match(stripped)
        if windows_match:
            size_or_dir = windows_match.group("size_or_dir")
            is_dir = size_or_dir.upper() == "<DIR>"
            return {
                "name": windows_match.group("name"),
                "permissions": None,
                "size": None if is_dir else int(size_or_dir),
                "date": (
                    f"{windows_match.group('date')} "
                    f"{windows_match.group('time')}"
                ),
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
    def _working_directory(
        self, ftp: FTP, path: str
    ) -> Generator[None, None, None]:
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

    def _try_mlst(
        self, ftp: FTP, remote_path: str
    ) -> tuple[dict[str, str] | None, bool]:
        try:
            response = ftp.sendcmd(f"MLST {remote_path}")
        except all_errors as exc:
            return None, not self._is_command_not_supported(exc)

        facts = self._parse_mlst_response(response)
        if not facts:
            return None, False
        return facts, True

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
        normalized = (path or "/").replace("\\", "/")
        return normalized or "/"

    def _join_remote_path(self, base_dir: str, raw_name: str) -> str:
        normalized_name = str(raw_name).replace("\\", "/")
        if (
            normalized_name.startswith("/")
            or re.match(r"^[A-Za-z]:/", normalized_name)
        ):
            return normalized_name
        if base_dir in {"", "/"}:
            return f"/{normalized_name.lstrip('/')}"
        return posixpath.join(base_dir.rstrip("/"), normalized_name)

    def _display_name(self, raw_name: str) -> str:
        normalized_name = str(raw_name).replace("\\", "/").rstrip("/")
        if "/" not in normalized_name:
            return normalized_name
        return posixpath.basename(normalized_name)

    def _format_modify_timestamp(self, value: str | None) -> str | None:
        if not value:
            return None
        for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M%S.%f"):
            with suppress(ValueError):
                return datetime.strptime(value, fmt).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
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

    @staticmethod
    def _is_command_not_supported(exc: Exception) -> bool:
        msg = str(exc)
        lower_msg = msg.lower()
        if any(
            keyword in lower_msg
            for keyword in (
                "not understood",
                "not recognized",
                "not implemented",
                "not supported",
                "unknown command",
            )
        ):
            return True
        return msg[:4] in ("500 ", "502 ", "504 ")

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

    def download(self, remote_path: str, local_path: str) -> Path:
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        with open(local, "wb") as file_obj:
            for chunk in self.download_stream(remote_path):
                file_obj.write(chunk)
        return local

    def _upload_fileobj(
        self, remote_dir: str, filename: str, file_obj: BinaryIO
    ) -> str:
        remote_path = f"{remote_dir.rstrip('/')}/{filename}"
        with self._connect() as ftp:
            ftp.cwd(remote_dir)
            ftp.storbinary(f"STOR {filename}", file_obj)
        return remote_path

    def upload(self, local_path: str, remote_dir: str) -> dict[str, str]:
        local = Path(local_path)
        with open(local, "rb") as file_obj:
            remote_path = self._upload_fileobj(
                remote_dir, local.name, file_obj
            )
        return {"status": "uploaded", "remote_path": remote_path}
