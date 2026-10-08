"""Credential-free Docker check for supervised detached Codex lifetime.

This starts no model turn and mounts no provider profile or host credential.
"""

import json
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

from laomedo.container_lease import LABEL_RUN, LABEL_TOKEN, inspect_exact
from laomedo.local_runner import AppServer, IMAGE, IMAGE_ID


def main() -> None:
    intended_temp = Path(tempfile.gettempdir()).resolve()
    temporary_root = intended_temp / "laomedo-exp22-detached"
    temporary_root.mkdir(exist_ok=True)
    if not temporary_root.resolve().is_relative_to(intended_temp):
        raise RuntimeError("temporary_root_outside_temp")
    image = subprocess.run(["docker", "image", "inspect", IMAGE,
                            "--format", "{{.Id}}"], capture_output=True,
                           text=True, timeout=15)
    if image.returncode or image.stdout.strip() != IMAGE_ID:
        raise RuntimeError("pinned_image_unavailable")
    run_id, token = str(uuid4()), uuid4().hex
    name = "laomedo-detached-check-" + uuid4().hex
    with tempfile.TemporaryDirectory(prefix="exp22-detach-",
                                     dir=temporary_root) as folder:
        if not Path(folder).resolve().is_relative_to(temporary_root.resolve()):
            raise RuntimeError("temporary_state_outside_temp")
        command = ["docker", "run", "--detach", "--rm", "-i", "--name", name,
                   "--label", f"{LABEL_RUN}={run_id}",
                   "--label", f"{LABEL_TOKEN}={token}",
                   "--pull=never", "--network", "none", "--read-only",
                   "--cap-drop", "ALL", "--user", "10001:10001",
                   "--tmpfs", "/home/runner/.codex:uid=10001,gid=10001",
                   IMAGE, "codex", "app-server", "--stdio"]
        server = None
        owned_after_loss = running_after_loss = cleanup_verified = False
        try:
            server = AppServer(command, Path(folder))
            initialized = server.request("initialize", {"clientInfo": {
                "name": "detached-preflight", "title": "Detached Preflight",
                "version": "0.1.0"}}, timeout=10)
            if "result" not in initialized:
                raise RuntimeError("initialize_failed")
            server.process.terminate()
            server.process.wait(timeout=5)
            time.sleep(.5)
            state, _ = inspect_exact(name, run_id, token)
            owned_after_loss = state == "owned"
            check = subprocess.run(["docker", "inspect", name, "--format",
                                    "{{.State.Running}}"], capture_output=True,
                                   text=True, timeout=10)
            running_after_loss = (check.returncode == 0 and
                                  check.stdout.strip() == "true")
        finally:
            if server is not None:
                server.close()
                cleanup_verified = inspect_exact(name, run_id, token)[0] == "absent"
            else:
                subprocess.run(["docker", "rm", "-f", name],
                               capture_output=True, timeout=15)
        result = {"image_id": IMAGE_ID,
                  "credential_mounted": False,
                  "model_turn_submitted": False,
                  "owned_after_attach_loss": owned_after_loss,
                  "running_after_attach_loss": running_after_loss,
                  "exact_cleanup_verified": cleanup_verified}
        print(json.dumps(result, sort_keys=True))
        if not all((owned_after_loss, running_after_loss, cleanup_verified)):
            raise RuntimeError("detached_preflight_failed")


if __name__ == "__main__":
    main()
