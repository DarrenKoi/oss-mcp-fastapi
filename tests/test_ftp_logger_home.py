import logging

from app.common.ftp_proxy.ftp_logger import RecentRecordsFileHandler


def test_recent_records_file_handler_keeps_only_latest_entries(tmp_path):
    log_path = tmp_path / "ftp_proxy.log"
    handler = RecentRecordsFileHandler(log_path, max_records=3)
    handler.setFormatter(logging.Formatter("%(message)s"))

    logger = logging.getLogger("tests.ftp_logger")
    logger.handlers = []
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(handler)

    try:
        for index in range(5):
            logger.info("entry-%s", index)
    finally:
        logger.removeHandler(handler)
        handler.close()

    assert log_path.read_text(encoding="utf-8").splitlines() == [
        "entry-2",
        "entry-3",
        "entry-4",
    ]
