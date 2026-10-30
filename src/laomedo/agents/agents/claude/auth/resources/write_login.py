"""Write one exact-length access-only record without waiting for pipe EOF."""

import json
import os
from pathlib import Path
import stat
import sys
import tempfile


def write_login(directory: Path, length: int, source) -> None:
    """Refuse refresh ownership and write only after the entire payload arrives."""
    if length <= 0 or directory.is_symlink():
        raise ValueError("login_write_refused")
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir():
        raise ValueError("login_write_refused")
    target = directory / ".credentials.json"
    if target.is_symlink():
        raise ValueError("login_write_refused")
    if target.exists():
        observed = target.lstat()
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ValueError("login_write_refused")
        with target.open(encoding="utf-8") as stream:
            old = json.load(stream)
        if old.get("claudeAiOauth", {}).get("refreshToken"):
            raise ValueError("login_write_refused")
    payload = bytearray()
    while len(payload) < length:
        part = source.read(min(65536, length - len(payload)))
        if not part:
            raise ValueError("login_input_incomplete")
        payload.extend(part)
    for path in directory.glob(".login-*"):
        observed = path.lstat()
        if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
            raise ValueError("login_write_refused")
        path.unlink()
    descriptor, pending = tempfile.mkstemp(prefix=".login-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        os.chmod(pending, 0o600)
        os.replace(pending, target)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)


if __name__ == "__main__":
    write_login(Path("/profile/config"), int(sys.argv[1]), sys.stdin.buffer)
