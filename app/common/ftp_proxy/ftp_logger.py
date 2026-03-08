from __future__ import annotations

from collections import deque
import logging
import os
from pathlib import Path
from typing import Literal


LoggerRole = Literal["server", "client"]

DEFAULT_LOG_DIR = Path(".logs") / "ftp_proxy"
MAX_LOG_RECORDS = 1000
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def get_ftp_proxy_logger(role: LoggerRole) -> logging.Logger:
    logger = logging.getLogger(f"ftp_proxy.{role}")
    logger.setLevel(_resolve_log_level())

    handler_name = f"ftp_proxy_{role}_file"
    if not any(handler.get_name() == handler_name for handler in logger.handlers):
        handler = _build_file_handler(role)
        if handler is not None:
            handler.set_name(handler_name)
            handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(handler)

    logger.propagate = True
    return logger


def _build_file_handler(role: LoggerRole) -> logging.Handler | None:
    log_path = _resolve_log_path(role)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return RecentRecordsFileHandler(
            log_path,
            max_records=_resolve_log_record_limit(),
        )
    except OSError:
        return None


def _resolve_log_level() -> int:
    level_name = os.getenv("FTP_PROXY_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def _resolve_log_path(role: LoggerRole) -> Path:
    specific_log_file = os.getenv(f"FTP_PROXY_{role.upper()}_LOG_FILE")
    if specific_log_file:
        return Path(specific_log_file).expanduser()

    log_dir = Path(
        os.getenv("FTP_PROXY_LOG_DIR", str(DEFAULT_LOG_DIR))
    ).expanduser()
    return log_dir / f"{role}.log"


def _resolve_log_record_limit() -> int:
    raw_limit = os.getenv("FTP_PROXY_LOG_RECORD_LIMIT", str(MAX_LOG_RECORDS))
    try:
        return max(int(raw_limit), 1)
    except ValueError:
        return MAX_LOG_RECORDS


class RecentRecordsFileHandler(logging.Handler):
    def __init__(self, log_path: Path, *, max_records: int):
        super().__init__()
        self.log_path = log_path
        self.max_records = max_records

    def emit(self, record: logging.LogRecord) -> None:
        try:
            rendered = f"{self.format(record)}\n"
            existing_records = self._read_existing_records()
            existing_records.append(rendered)
            with self.log_path.open("w", encoding="utf-8") as log_file:
                log_file.writelines(existing_records)
        except OSError:
            self.handleError(record)

    def _read_existing_records(self) -> deque[str]:
        records: deque[str] = deque(maxlen=self.max_records)
        if not self.log_path.exists():
            return records
        with self.log_path.open("r", encoding="utf-8") as log_file:
            for line in log_file:
                records.append(line)
        return records
