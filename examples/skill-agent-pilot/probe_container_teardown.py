"""No-model Docker probe for owned-container cleanup after client termination."""

from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from laomedo.local_runner import AppServer, IMAGE


def main():
    name = "laomedo-codex-review-" + uuid4().hex
    command = ["docker", "run", "--rm", "-i", "--name", name, "--pull=never",
               IMAGE, "sh", "-c", "sleep 60"]
    with tempfile.TemporaryDirectory(prefix="laomedo-teardown-") as directory:
        app = AppServer(command, Path(directory))
        try:
            for _ in range(50):
                state = subprocess.run(["docker", "inspect", "--format", "{{.State.Running}}", name],
                                       capture_output=True, text=True, timeout=10)
                if state.returncode == 0 and state.stdout.strip() == "true":
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("owned_container_never_started")
        finally:
            app.close()
        absent = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=10)
        if absent.returncode == 0:
            raise RuntimeError("owned_container_survived_close")
        print("owned_container_removed; model_turns_submitted=0")


if __name__ == "__main__":
    main()
