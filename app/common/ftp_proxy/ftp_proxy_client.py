from pathlib import Path
from typing import Any

import httpx


class FTPProxyClient:
    """SDK for office users to interact with the FTP proxy server.

    Usage:
        client = FTPProxyClient(
            proxy_url="http://internal-server:8000",
            ftp_host="fab-tool-01",
            ftp_user="operator",
            ftp_password="secret",
        )
        files = client.list_files("/data")
        client.download("/data/report.csv", "./downloads/report.csv")
        client.upload("./local_file.txt", "/data")
    """

    LIST_KEYS = ("entries", "files", "items", "listing", "data")
    PATH_KEYS = ("path", "directory", "folder", "cwd")
    STRATEGY_KEYS = ("strategy", "method", "listing_method", "source")

    def __init__(
        self,
        proxy_url: str,
        ftp_host: str,
        ftp_port: int = 21,
        ftp_user: str = "anonymous",
        ftp_password: str = "",
    ):
        self.proxy_url = proxy_url.rstrip("/")
        self.ftp_host = ftp_host
        self.ftp_port = ftp_port
        self.ftp_user = ftp_user
        self.ftp_password = ftp_password

    def _ftp_params(self) -> dict:
        return {
            "host": self.ftp_host,
            "port": self.ftp_port,
            "user": self.ftp_user,
            "password": self.ftp_password,
        }

    def list_files(self, path: str = "/") -> list[dict[str, Any]]:
        return self.list_files_response(path)["entries"]

    def list_files_response(self, path: str = "/") -> dict[str, Any]:
        params = {**self._ftp_params(), "path": path}
        resp = httpx.get(f"{self.proxy_url}/ftp-proxy/v1/list", params=params)
        resp.raise_for_status()
        return self._normalize_list_response(resp.json(), requested_path=path)

    def _normalize_list_response(self, payload: Any, requested_path: str) -> dict[str, Any]:
        entries_payload = self._extract_entries(payload)
        if entries_payload is None:
            raise ValueError("FTP proxy list response did not include any entries")

        attempts = payload.get("attempts") if isinstance(payload, dict) and isinstance(payload.get("attempts"), list) else []
        response_path = self._pick_first(payload, self.PATH_KEYS) if isinstance(payload, dict) else None
        strategy = self._pick_first(payload, self.STRATEGY_KEYS) if isinstance(payload, dict) else None

        return {
            "path": response_path or requested_path,
            "entries": [self._normalize_entry(entry) for entry in entries_payload],
            "strategy": strategy,
            "attempts": attempts,
            "raw": payload,
        }

    def _extract_entries(self, payload: Any) -> list[Any] | None:
        if isinstance(payload, list):
            return payload

        if not isinstance(payload, dict):
            return None

        for key in self.LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = self._extract_entries(value)
                if nested is not None:
                    return nested

        for key, value in payload.items():
            if key == "attempts":
                continue
            if isinstance(value, list):
                return value

        if {"name", "filename", "file_name", "path", "pathname"} & payload.keys():
            return [payload]

        return None

    def _normalize_entry(self, entry: Any) -> dict[str, Any]:
        if isinstance(entry, str):
            return {
                "name": self._display_name(entry),
                "permissions": None,
                "size": None,
                "date": None,
                "is_dir": None,
                "raw": entry,
            }

        if not isinstance(entry, dict):
            return {
                "name": str(entry),
                "permissions": None,
                "size": None,
                "date": None,
                "is_dir": None,
                "raw": entry,
            }

        normalized = dict(entry)
        name = self._pick_first(
            entry,
            ("name", "filename", "file_name", "basename", "path", "pathname", "full_name"),
        )
        entry_type = self._pick_first(entry, ("type", "entry_type", "kind"))
        modified = self._pick_first(entry, ("date", "modified", "modify", "mtime", "timestamp"))
        permissions = self._pick_first(entry, ("permissions", "mode", "perm", "unix.mode"))
        size = self._to_int(self._pick_first(entry, ("size", "filesize", "length", "file_size")))
        is_dir = self._coerce_is_dir(entry.get("is_dir"))
        if is_dir is None:
            is_dir = self._coerce_is_dir(entry.get("directory"))
        if is_dir is None:
            is_dir = self._coerce_is_dir(entry.get("dir"))
        if is_dir is None:
            is_dir = self._coerce_is_dir(entry_type)

        normalized.update(
            {
                "name": self._display_name(name),
                "permissions": permissions,
                "size": size,
                "date": modified,
                "is_dir": is_dir,
            }
        )
        return normalized

    def _pick_first(self, data: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    def _display_name(self, value: Any) -> str:
        text = str(value or "").strip().replace("\\", "/").rstrip("/")
        if "/" not in text:
            return text
        return text.rsplit("/", maxsplit=1)[-1]

    def _to_int(self, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _coerce_is_dir(self, value: Any) -> bool | None:
        if isinstance(value, bool) or value is None:
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "dir", "directory", "folder", "cdir", "pdir"}:
            return True
        if text in {"0", "false", "no", "file"}:
            return False
        return None

    def download(self, remote_path: str, local_path: str) -> Path:
        params = {**self._ftp_params(), "path": remote_path}
        local = Path(local_path)
        local.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", f"{self.proxy_url}/ftp-proxy/v1/download", params=params) as resp:
            resp.raise_for_status()
            with open(local, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return local

    def upload(self, local_path: str, remote_dir: str) -> dict:
        params = {**self._ftp_params(), "path": remote_dir}
        local = Path(local_path)
        with open(local, "rb") as f:
            files = {"file": (local.name, f)}
            resp = httpx.post(f"{self.proxy_url}/ftp-proxy/v1/upload", params=params, files=files)
        resp.raise_for_status()
        return resp.json()
