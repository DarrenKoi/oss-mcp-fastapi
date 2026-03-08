import threading

from app.common.ftp_proxy.ftp_batch_downloader import FTPBatchDownloader
from app.common.ftp_proxy.ftp_direct_client import FTPDirectClient
from tests.ftp_fakes import FakeFTP, patch_connect_multi


class TestBatchDownloadSuccess:
    def test_downloads_from_multiple_hosts(self, monkeypatch, tmp_path):
        fakes = {
            "10.0.0.1": FakeFTP(downloads={"/data/log.csv": b"data-from-1"}),
            "10.0.0.2": FakeFTP(downloads={"/data/log.csv": b"data-from-2"}),
            "10.0.0.3": FakeFTP(downloads={"/data/log.csv": b"data-from-3"}),
        }
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader()
        result = downloader.batch_download(
            hosts=["10.0.0.1", "10.0.0.2", "10.0.0.3"],
            remote_path="/data/log.csv",
            base_dir=str(tmp_path),
        )

        assert result.total == 3
        assert result.succeeded == 3
        assert result.failed == 0
        assert result.elapsed_seconds > 0

        for host, content in [
            ("10.0.0.1", b"data-from-1"),
            ("10.0.0.2", b"data-from-2"),
            ("10.0.0.3", b"data-from-3"),
        ]:
            downloaded = tmp_path / host / "log.csv"
            assert downloaded.exists()
            assert downloaded.read_bytes() == content

    def test_files_organized_by_host_ip(self, monkeypatch, tmp_path):
        fakes = {
            "192.168.1.10": FakeFTP(
                downloads={"/recipe.dat": b"recipe-a"}
            ),
            "192.168.1.20": FakeFTP(
                downloads={"/recipe.dat": b"recipe-b"}
            ),
        }
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader()
        downloader.batch_download(
            hosts=["192.168.1.10", "192.168.1.20"],
            remote_path="/recipe.dat",
            base_dir=str(tmp_path),
        )

        assert (tmp_path / "192.168.1.10" / "recipe.dat").read_bytes() == b"recipe-a"
        assert (tmp_path / "192.168.1.20" / "recipe.dat").read_bytes() == b"recipe-b"


class TestBatchDownloadPartialFailure:
    def test_partial_failure_counts(self, monkeypatch, tmp_path):
        fakes = {
            "10.0.0.1": FakeFTP(downloads={"/data/log.csv": b"ok"}),
            "10.0.0.2": FakeFTP(downloads={}),  # file not found
        }
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader()
        result = downloader.batch_download(
            hosts=["10.0.0.1", "10.0.0.2"],
            remote_path="/data/log.csv",
            base_dir=str(tmp_path),
        )

        assert result.total == 2
        assert result.succeeded == 1
        assert result.failed == 1

        success = [r for r in result.results if r.status == "success"]
        failed = [r for r in result.results if r.status == "failed"]
        assert len(success) == 1
        assert success[0].host == "10.0.0.1"
        assert success[0].local_path is not None
        assert len(failed) == 1
        assert failed[0].host == "10.0.0.2"
        assert failed[0].error is not None

    def test_successful_downloads_unaffected_by_failures(
        self, monkeypatch, tmp_path
    ):
        fakes = {
            "10.0.0.1": FakeFTP(downloads={}),  # fails
            "10.0.0.2": FakeFTP(downloads={"/f.bin": b"good"}),
        }
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader()
        downloader.batch_download(
            hosts=["10.0.0.1", "10.0.0.2"],
            remote_path="/f.bin",
            base_dir=str(tmp_path),
        )

        assert (tmp_path / "10.0.0.2" / "f.bin").read_bytes() == b"good"


class TestBatchDownloadCallback:
    def test_on_complete_fires_for_each_host(self, monkeypatch, tmp_path):
        fakes = {
            "h1": FakeFTP(downloads={"/a.txt": b"1"}),
            "h2": FakeFTP(downloads={"/a.txt": b"2"}),
        }
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        events: list[str] = []
        lock = threading.Lock()

        def on_complete(tool_result):
            with lock:
                events.append(tool_result.host)

        downloader = FTPBatchDownloader()
        downloader.batch_download(
            hosts=["h1", "h2"],
            remote_path="/a.txt",
            base_dir=str(tmp_path),
            on_complete=on_complete,
        )

        assert sorted(events) == ["h1", "h2"]


class TestBatchDownloadConcurrency:
    def test_max_workers_capped_at_limit(self, monkeypatch, tmp_path):
        fakes = {"h1": FakeFTP(downloads={"/f": b"x"})}
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader()
        result = downloader.batch_download(
            hosts=["h1"],
            remote_path="/f",
            base_dir=str(tmp_path),
            max_workers=100,  # should be capped to MAX_WORKERS_CAP
        )
        assert result.succeeded == 1

    def test_respects_max_workers(self, monkeypatch, tmp_path):
        peak_lock = threading.Lock()
        active = 0
        peak = 0

        original_download_one = FTPBatchDownloader._download_one

        def tracked_download(self, host, remote_path, base_dir):
            nonlocal active, peak
            with peak_lock:
                active += 1
                if active > peak:
                    peak = active
            try:
                return original_download_one(self, host, remote_path, base_dir)
            finally:
                with peak_lock:
                    active -= 1

        monkeypatch.setattr(
            FTPBatchDownloader, "_download_one", tracked_download
        )

        hosts = [f"h{i}" for i in range(10)]
        fakes = {h: FakeFTP(downloads={"/f": b"x"}) for h in hosts}
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader()
        result = downloader.batch_download(
            hosts=hosts,
            remote_path="/f",
            base_dir=str(tmp_path),
            max_workers=2,
        )

        assert result.succeeded == 10
        assert peak <= 2


class TestBatchDownloadCredentials:
    def test_passes_credentials_to_client(self, monkeypatch, tmp_path):
        created_clients: list[FTPDirectClient] = []
        original_init = FTPDirectClient.__init__

        def tracking_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            created_clients.append(self)

        monkeypatch.setattr(FTPDirectClient, "__init__", tracking_init)

        fakes = {"host1": FakeFTP(downloads={"/x": b"d"})}
        patch_connect_multi(monkeypatch, FTPDirectClient, fakes)

        downloader = FTPBatchDownloader(
            port=2121,
            user="fab",
            password="secret",
            timeout=10,
            encoding="cp949",
        )
        downloader.batch_download(
            hosts=["host1"],
            remote_path="/x",
            base_dir=str(tmp_path),
        )

        assert len(created_clients) == 1
        c = created_clients[0]
        assert c.host == "host1"
        assert c.port == 2121
        assert c.user == "fab"
        assert c.password == "secret"
        assert c.timeout == 10
        assert c.encoding == "cp949"
