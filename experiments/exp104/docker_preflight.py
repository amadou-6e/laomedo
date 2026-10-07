"""Local-only, one-shot Docker diagnostic for EXP-104 amendment 10."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

from laomedo.container_lease import cleanup_exact, inspect_exact


NAME = "laomedo-exp104-local-preflight-20261007"
RUN = "exp104-local-preflight-20261007"
TOKEN = "exp104-local-preflight-launch"
IMAGE = "sha256:bb8009c87ab69e751a1dd2c6c7f8abaae3d9fce8e072802d4a23c95594d16d84"


def main() -> None:
    if inspect_exact(NAME, RUN, TOKEN)[0] != "absent":
        raise RuntimeError("preflight_name_not_absent")
    launched = subprocess.run([
        "docker", "run", "-d", "--name", NAME, "--network", "none",
        "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--memory", "64m", "--pids-limit", "32",
        "--label", "laomedo.run_id=" + RUN,
        "--label", "laomedo.launch_token=" + TOKEN,
        IMAGE, "python", "-c", "import time; time.sleep(180)"],
        capture_output=True, timeout=30)
    result = {"kind": "local_docker_preflight", "returncode": launched.returncode,
              "stderr": launched.stderr.decode(errors="replace"),
              "inspect_state": inspect_exact(NAME, RUN, TOKEN)[0]}
    try:
        if result["returncode"] or result["inspect_state"] != "owned":
            raise RuntimeError("docker_preflight_failed")
    finally:
        result["cleanup_verified"], result["cleanup_state"] = cleanup_exact(
            NAME, RUN, TOKEN)
        Path(__file__).with_name("docker-preflight-observation.json").write_text(
            json.dumps(result, sort_keys=True, indent=2) + "\n",
            encoding="utf-8", newline="\n")
    if not result["cleanup_verified"]:
        raise RuntimeError("docker_preflight_cleanup_unverified")
    print(json.dumps({"returncode": result["returncode"],
                      "inspect_state": result["inspect_state"],
                      "cleanup_verified": result["cleanup_verified"]}))


if __name__ == "__main__":
    main()
