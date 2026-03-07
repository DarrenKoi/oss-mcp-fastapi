from pathlib import Path

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

    def list_files(self, path: str = "/") -> list[dict]:
        params = {**self._ftp_params(), "path": path}
        resp = httpx.get(f"{self.proxy_url}/ftp-proxy/v1/list", params=params)
        resp.raise_for_status()
        return resp.json()["entries"]

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
