from __future__ import annotations

import posixpath
import re
from typing import Any


_REMOTE_DRIVE_PATTERN = re.compile(r"^[A-Za-z]:(?:/.*)?$")
_REMOTE_DRIVE_ROOT_PATTERN = re.compile(
    r"^(?P<drive>[A-Za-z]:)(?P<rest>/.*)?$"
)


def is_remote_absolute(path: Any) -> bool:
    text = str(path or "").strip().replace("\\", "/")
    return text.startswith("/") or bool(_REMOTE_DRIVE_PATTERN.match(text))


def normalize_remote_path(path: Any, *, default: str = "/") -> str:
    text = str(path or "").strip().replace("\\", "/")
    if not text:
        text = default
    if not text:
        return ""

    drive_match = _REMOTE_DRIVE_ROOT_PATTERN.match(text)
    if drive_match:
        drive = drive_match.group("drive")
        rest = drive_match.group("rest")
        if not rest:
            return f"{drive}/"
        normalized_rest = posixpath.normpath(rest)
        if normalized_rest == ".":
            return f"{drive}/"
        if not normalized_rest.startswith("/"):
            normalized_rest = f"/{normalized_rest}"
        return f"{drive}{normalized_rest}"

    normalized = posixpath.normpath(text)
    if text.startswith("/") and not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized == ".":
        return default if default else ""
    return normalized


def join_remote_path(base_dir: Any, raw_name: Any) -> str:
    normalized_name = normalize_remote_path(raw_name, default="")
    if not normalized_name:
        return normalize_remote_path(base_dir)
    if is_remote_absolute(normalized_name):
        return normalized_name

    normalized_base = normalize_remote_path(base_dir)
    if normalized_base in {"", "/"}:
        return f"/{normalized_name.lstrip('/')}"
    return posixpath.join(
        normalized_base.rstrip("/"), normalized_name.lstrip("/")
    )


def remote_basename(path: Any, *, default: str = "") -> str:
    normalized = normalize_remote_path(path, default="").rstrip("/")
    if not normalized:
        return default
    if re.match(r"^[A-Za-z]:$", normalized):
        return default
    return posixpath.basename(normalized) or default
