import posixpath
from typing import Any


class FTPListResponseNormalizer:
    """프록시 응답 형태가 조금씩 달라도 공통 목록 포맷으로 맞춘다."""

    LIST_KEYS = ("entries", "files", "items", "listing", "data")
    PATH_KEYS = ("path", "directory", "folder", "cwd")
    STRATEGY_KEYS = ("strategy", "method", "listing_method", "source")

    def _normalize_list_response(
        self, payload: Any, requested_path: str
    ) -> dict[str, Any]:
        # 응답에서 실제 목록 배열과 부가 메타데이터를 뽑아
        # SDK가 항상 같은 키 구조를 보게 만든다.
        entries_payload = self._extract_entries(payload)
        if entries_payload is None:
            raise ValueError(
                "FTP list response did not include any entries"
            )

        attempts = []
        if isinstance(payload, dict):
            if isinstance(payload.get("attempts"), list):
                attempts = payload["attempts"]

        response_path = None
        strategy = None
        if isinstance(payload, dict):
            response_path = self._pick_first(payload, self.PATH_KEYS)
            strategy = self._pick_first(payload, self.STRATEGY_KEYS)

        return {
            "path": response_path or requested_path,
            "entries": [
                self._normalize_entry(entry)
                for entry in entries_payload
            ],
            "strategy": strategy,
            "attempts": attempts,
            "raw": payload,
        }

    def _extract_entries(self, payload: Any) -> list[Any] | None:
        # 서버 구현마다 entries/files/items 등 키 이름이 다를 수 있어서
        # 후보 키를 순서대로 훑고, 중첩 딕셔너리도 재귀적으로 살핀다.
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

        if {
            "name",
            "filename",
            "file_name",
            "path",
            "pathname",
        } & payload.keys():
            return [payload]

        return None

    def _normalize_entry(self, entry: Any) -> dict[str, Any]:
        # 문자열만 오는 단순 목록 응답도 후속 코드에서 같은 형태로
        # 다룰 수 있게 dict 구조로 승격한다.
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
            (
                "name",
                "filename",
                "file_name",
                "basename",
                "path",
                "pathname",
                "full_name",
            ),
        )
        entry_type = self._pick_first(
            entry, ("type", "entry_type", "kind")
        )
        modified = self._pick_first(
            entry,
            ("date", "modified", "modify", "mtime", "timestamp"),
        )
        permissions = self._pick_first(
            entry, ("permissions", "mode", "perm", "unix.mode")
        )
        size = self._to_int(
            self._pick_first(
                entry, ("size", "filesize", "length", "file_size")
            )
        )
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

    def _pick_first(
        self, data: dict[str, Any], keys: tuple[str, ...]
    ) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    def _display_name(self, value: Any) -> str:
        text = str(value or "").strip().replace("\\", "/").rstrip("/")
        if "/" not in text:
            return text
        return posixpath.basename(text)

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
        if text in {
            "1",
            "true",
            "yes",
            "dir",
            "directory",
            "folder",
            "cdir",
            "pdir",
        }:
            return True
        if text in {"0", "false", "no", "file"}:
            return False
        return None
