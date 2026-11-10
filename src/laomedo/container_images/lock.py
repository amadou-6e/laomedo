"""Cross-process exclusion released by the operating system after a crash."""

import errno
import os
import time

from laomedo.container_images.errors import ImageBuildError


class ImageBuildLock:
    """Lock one daemon/image pair; never delete another process's lock file."""

    def __init__(self, path, *, deadline, cancelled=None):
        self.path, self.deadline, self.cancelled = path, deadline, cancelled
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        try:
            while True:
                if self.cancelled is not None and self.cancelled.is_set():
                    raise ImageBuildError("build_cancelled")
                if time.monotonic() >= self.deadline:
                    raise ImageBuildError("build_lock_timeout")
                try:
                    self.stream.seek(0)
                    if os.name == "nt":
                        import msvcrt

                        msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl

                        fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except OSError as error:
                    if error.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(0.05)
        except BaseException:
            self.stream.close()
            raise

    def __exit__(self, *_):
        if os.name == "nt":
            import msvcrt

            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        self.stream.close()
