"""Read asynchronous lease results and drain test-owned cleanup before teardown."""

import json
from pathlib import Path
import time

from laomedo.host.leases.service import LeaseService


def result(directory: Path) -> dict:
    """Read a complete result despite a transient Windows rename/read race."""
    path = directory.joinpath("result.json")
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, PermissionError):
            time.sleep(0.01)
    raise AssertionError("lease result not written")


def wait_for_cleanup(service: LeaseService) -> None:
    """Keep fixture files alive until their asynchronous cleanup has finished."""
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        with service._finishing_lock:
            if not service._finishing:
                return
        time.sleep(0.01)
    raise AssertionError("test-owned lease cleanup did not finish")
