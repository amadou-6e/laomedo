"""A separate real lease service process for normal container lifecycle tests."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


class LeaseServiceProcess:
    """Run a synthetic lease service; this fixture does not prove tree-kill recovery."""

    def __init__(self):
        """Reserve disposable state outside all implementation checkouts."""
        self.directory = tempfile.TemporaryDirectory(prefix="laomedo-lease-test-")
        self.state = Path(self.directory.name)
        self.process = None

    def __enter__(self):
        """Wait for this service's actual heartbeat before tests register containers."""
        allowed = {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "HOME",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
            "DOCKER_CONFIG",
            "DOCKER_CERT_PATH",
        }
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in allowed
        }
        environment.update(
            DOCKER_CONTEXT="desktop-linux",
            PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"),
        )
        self.process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "laomedo.host.leases.service_cli",
                "serve",
                "--state",
                str(self.state),
            ],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + 15.0
        try:
            while not (self.state / "service.alive").exists():
                if self.process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("test_lease_service_unavailable")
                time.sleep(0.05)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, kind, value, traceback):
        """Stop only this fixture's service after callers finish their containers."""
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self.directory.cleanup()
