from contextlib import contextmanager
from ftplib import FTP
from typing import Generator, BinaryIO


class FTPProxyServer:
    """Proxy server that connects to fab FTP servers and serves files to office users."""

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
            ftp.quit()

    def list_dir(self, path: str = "/") -> list[dict]:
        with self._connect() as ftp:
            entries = []
            lines: list[str] = []
            ftp.cwd(path)
            ftp.retrlines("LIST", lines.append)
            for line in lines:
                parts = line.split(None, 8)
                if len(parts) < 9:
                    continue
                entries.append({
                    "permissions": parts[0],
                    "size": int(parts[4]),
                    "date": f"{parts[5]} {parts[6]} {parts[7]}",
                    "name": parts[8],
                    "is_dir": parts[0].startswith("d"),
                })
            return entries

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
