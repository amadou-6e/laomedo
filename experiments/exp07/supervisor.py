"""Independent host-side lease supervisor for the disposable EXP-07 stage."""

import json
import os
from pathlib import Path
import subprocess
import time
from urllib import request


BACKEND = "laomedo-exp07-backend-20261002"
WORKER = "laomedo-exp07-worker-20261002"
URL = "http://127.0.0.1:17867/revoke"
RENEW_URL = "http://127.0.0.1:17867/renew"
TOKEN = os.environ["CANARY_GRANT"]
REPORT = Path(os.environ["EXP07_SUPERVISOR_REPORT"])


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          timeout=10, check=False)


while True:
    state = docker("inspect", "--format", "{{.State.Status}}", BACKEND)
    if state.returncode != 0 or state.stdout.strip() != "running":
        detected_ns = time.time_ns()
        req = request.Request(URL, data=b"revoke", method="POST",
                              headers={"X-Test-Grant": TOKEN})
        try:
            with request.urlopen(req, timeout=3) as response:
                revoked = response.status == 200
        except OSError:
            revoked = False
        kill = docker("kill", WORKER)
        report = {"detected_ns": detected_ns, "revoked": revoked,
                  "kill_returncode": kill.returncode,
                  "worker_state": docker("inspect", "--format", "{{.State.Status}}", WORKER).stdout.strip()}
        REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        break
    req = request.Request(RENEW_URL, data=b"renew", method="POST",
                          headers={"X-Test-Grant": TOKEN})
    try:
        with request.urlopen(req, timeout=3) as response:
            if response.status != 200:
                raise RuntimeError("lease renewal failed")
    except OSError:
        # Expiry at the independent canary remains the fallback bound.
        pass
    time.sleep(0.2)
