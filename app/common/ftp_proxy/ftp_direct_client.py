import asyncio
import posixpath
import re
from contextlib import asynccontextmanager, contextmanager, suppress
from datetime import datetime
from ftplib import FTP, all_errors
from pathlib import Path
from typing import Any, AsyncGenerator, BinaryIO, Generator


class FTPDirectClient:
    """FTP 서버에 직접 붙어 목록 조회, 다운로드, 업로드를 수행한다."""

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

    def _create_and_login_ftp(self) -> FTP:
        ftp = FTP(timeout=self.timeout)
        if self.encoding:
            ftp.encoding = self.encoding
        ftp.connect(self.host, self.port, timeout=self.timeout)
        ftp.login(self.user, self.password)
        return ftp

    @contextmanager
    def _connect(self) -> Generator[FTP, None, None]:
        ftp = self._create_and_login_ftp()
        try:
            yield ftp
        finally:
            with suppress(all_errors):
                ftp.quit()

    @asynccontextmanager
    async def _aconnect(self) -> AsyncGenerator[FTP, None]:
        ftp = await asyncio.to_thread(self._create_and_login_ftp)
        try:
            yield ftp
        finally:
            with suppress(all_errors):
                await asyncio.to_thread(ftp.quit)

    def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_files_response(path)["entries"]

    def list_files_response(self, path: str = "/") -> dict[str, Any]:
        normalized_path = self._normalize_path(path)
        attempts: list[dict[str, Any]] = []
        first_empty: dict[str, Any] | None = None

        with self._connect() as ftp:
            # FTP 서버마다 지원하는 명령이 달라서,
            # 성공할 때까지 여러 조회 전략을 순차적으로 시도한다.
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
        # MLST 지원 여부는 서버 단위 특성이라 첫 실패 후에는
        # 같은 연결에서 반복 호출하지 않도록 상태를 이어받는다.
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
        # NLST는 이름만 주기 때문에 가능하면 MLST/SIZE/CWD 테스트를 섞어
        # 파일 크기와 디렉터리 여부를 최대한 복원한다.
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

        # LIST 출력은 서버 OS에 따라 형식이 다르므로
        # 유닉스 형식과 윈도우 형식을 각각 파싱한다.
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
            # 명령 자체를 모르는 서버라면 이후 호출을 생략할 수 있게
            # "지원 여부" 플래그를 함께 반환한다.
            return None, not self._is_command_not_supported(exc)

        facts = self._parse_mlst_response(response)
        if not facts:
            return None, True
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
        normalized = str(path or "/").strip().replace("\\", "/")
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
        normalized_name = (
            str(raw_name).strip().replace("\\", "/").rstrip("/")
        )
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
                # 메모리에 파일 전체를 올리지 않고 일정 크기씩 바로 흘려보낸다.
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

    async def alist_files(self, path: str = "/") -> list[dict[str, Any]]:
        return (await self.alist_files_response(path))["entries"]

    async def alist_files_response(self, path: str = "/") -> dict[str, Any]:
        return await asyncio.to_thread(self.list_files_response, path)

    async def adownload_stream(self, path: str) -> AsyncGenerator[bytes, None]:
        gen = self.download_stream(path)
        sentinel = object()
        try:
            while True:
                # 동기 generator를 스레드로 감싸서 FastAPI async 경로에서도
                # 같은 다운로드 로직을 재사용한다.
                chunk = await asyncio.to_thread(next, gen, sentinel)
                if chunk is sentinel:
                    break
                yield chunk
        finally:
            await asyncio.to_thread(gen.close)

    async def adownload(self, remote_path: str, local_path: str) -> Path:
        return await asyncio.to_thread(self.download, remote_path, local_path)

    async def aupload(self, local_path: str, remote_dir: str) -> dict[str, str]:
        return await asyncio.to_thread(self.upload, local_path, remote_dir)
