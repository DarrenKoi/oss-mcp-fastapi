import os


DEFAULT_PROXY_URL = "http://127.0.0.1:8000"


def default_proxy_url() -> str:
    return os.getenv("FTP_PROXY_URL", DEFAULT_PROXY_URL).rstrip("/")
