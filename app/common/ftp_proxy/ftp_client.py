from contextlib import contextmanager
from ftplib import FTP
from io import BytesIO
from typing import Generator, BinaryIO


@contextmanager
def ftp_connection(
    host: str,
    port: int = 21,
    user: str = "anonymous",
    password: str = "",
) -> Generator[FTP, None, None]:
    ftp = FTP()
    ftp.connect(host, port)
    ftp.login(user, password)
    try:
        yield ftp
    finally:
        ftp.quit()


def list_dir(ftp: FTP, path: str = "/") -> list[dict]:
    entries = []
    lines = []
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


def download_stream(ftp: FTP, path: str) -> Generator[bytes, None, None]:
    ftp.voidcmd("TYPE I")
    with ftp.transfercmd(f"RETR {path}") as conn:
        while True:
            chunk = conn.recv(8192)
            if not chunk:
                break
            yield chunk
    ftp.voidresp()


def upload_file(ftp: FTP, path: str, file: BinaryIO) -> None:
    ftp.storbinary(f"STOR {path}", file)
