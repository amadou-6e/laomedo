"""Exact owned-container cleanup for real Docker integration checks."""

import json
from pathlib import Path
import re
import secrets
import subprocess
import tempfile


class DockerTestContainer:
    """Remove this check's exact labelled container even if its client times out."""

    def __init__(self):
        """Reserve a fresh client-side receipt, inaccessible inside the container."""
        self.directory = tempfile.TemporaryDirectory(
            prefix="laomedo-container-receipt-"
        )
        self.receipt = Path(self.directory.name) / "container.id"
        self.token = secrets.token_hex(16)

    def __enter__(self):
        """Expose only this unique invocation's Docker argument prefix."""
        return self

    def arguments(self):
        """Record Docker's real container ID; no host receipt is mounted."""
        return [
            "docker",
            "--context",
            "desktop-linux",
            "run",
            "--rm",
            "--cidfile",
            str(self.receipt),
            "--label",
            "laomedo.test=" + self.token,
        ]

    def __exit__(self, kind, value, traceback):
        """Verify the label before removing the exact ID, and confirm absence."""
        try:
            if not self.receipt.exists():
                return
            identity = self.receipt.read_text(encoding="ascii").strip()
            if not re.fullmatch(r"[0-9a-f]{64}", identity):
                raise RuntimeError("test_container_receipt_invalid")
            command = ["docker", "--context", "desktop-linux"]
            result = subprocess.run(
                command + ["inspect", identity], capture_output=True, timeout=15
            )
            if result.returncode:
                if b"no such object:" in result.stderr.lower():
                    return
                raise RuntimeError("test_container_cleanup_unconfirmed")
            entry = json.loads(result.stdout)[0]
            if (
                entry["Id"] != identity
                or (entry["Config"].get("Labels") or {}).get("laomedo.test")
                != self.token
            ):
                raise RuntimeError("test_container_receipt_mismatch")
            removed = subprocess.run(
                command + ["rm", "--force", identity], capture_output=True, timeout=15
            )
            if removed.returncode:
                raise RuntimeError("test_container_cleanup_unconfirmed")
            absent = subprocess.run(
                command + ["inspect", identity], capture_output=True, timeout=15
            )
            if (
                absent.returncode == 0
                or b"no such object:" not in absent.stderr.lower()
            ):
                raise RuntimeError("test_container_cleanup_unconfirmed")
        finally:
            self.directory.cleanup()
