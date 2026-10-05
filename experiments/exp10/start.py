"""Start the synthetic runner and disposable pinned Langflow backend."""

import os
from pathlib import Path
import socket
import subprocess
import sys
import time


state = Path("/state")
(state / "token").write_text("synthetic-exp10-token", encoding="utf-8")
mock_log = (state / "mock.log").open("a", encoding="utf-8")
subprocess.Popen([sys.executable, "/experiments/exp10/mock_runner.py"],
                 stdout=mock_log, stderr=subprocess.STDOUT, start_new_session=True)
for _ in range(50):
    try:
        with socket.create_connection(("127.0.0.1", 18740), timeout=0.2):
            break
    except OSError:
        time.sleep(0.1)
    else:
        break
else:
    raise RuntimeError("synthetic runner did not start")
os.execvp("langflow", ["langflow", "run"])
