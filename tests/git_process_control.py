"""Internal child-process controls; never a provider or source integration demo."""

import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    mode = sys.argv[1]
    if mode == "emit":
        sys.stdout.buffer.write(b"x" * int(sys.argv[2]))
        sys.stdout.buffer.flush()
        time.sleep(float(sys.argv[3]))
    elif mode == "exit":
        raise SystemExit(7)
    elif mode == "wait":
        time.sleep(float(sys.argv[2]))
    elif mode == "cache":
        with Path(sys.argv[2]).open("wb") as stream:
            stream.truncate(128 * 1024 * 1024 + 1)
        time.sleep(60)
    elif mode == "descendant":
        process = subprocess.Popen([sys.executable, __file__, "wait", "60"])
        Path(sys.argv[2]).write_text(
            json.dumps({"pid": process.pid, "parent_pid": os.getpid()}),
            encoding="utf-8",
        )
        time.sleep(60)
    else:
        raise ValueError("unknown internal child control")


if __name__ == "__main__":
    main()
