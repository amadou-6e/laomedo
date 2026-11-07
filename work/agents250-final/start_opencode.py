"""Compose the real isolated OpenCode provider for local acceptance, without caps."""

import json
import os
import socket
import subprocess
from pathlib import Path


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    evidence = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((evidence / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    with socket.socket() as check:
        check.bind(("127.0.0.1", 18817))
    image = "laomedo-opencode-controller:1.18.33"
    image_id = subprocess.check_output(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True
    ).strip()
    launcher = state / "serve_opencode.py"
    launcher.write_text(
        """from functools import partial
from pathlib import Path
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.agents.opencode.boundary import IsolatedOpenCode
from laomedo.host.runner.http.server import RunnerServer
state = Path("""
        + repr(str(state))
        + """)
factory = partial(IsolatedOpenCode,profile=state/'opencode-profile',image="""
        + repr(image)
        + """,image_id="""
        + repr(image_id)
        + """)
agent = OpenCodeAgent(state/'opencode',state/'registry',state/'workspace/content',transport_factory=factory,lease_service=state/'lease')
with RunnerServer(agent,port=18817) as server:
    server.serve_forever()
""",
        encoding="utf-8",
    )
    env = os.environ | {
        "PYTHONPATH": str(root / ".tools/agent-refactor-205/src"),
        "LAOMEDO_AGENT_ACTIVITY_DB": str(state / "activity.db"),
    }
    with (state / "opencode.log").open("wb") as output:
        proc = subprocess.Popen(
            [
                "C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe",
                str(launcher),
            ],
            env=env,
            cwd=root / ".tools/agent-refactor-205",
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    records = json.loads((state / "processes.json").read_text(encoding="utf-8"))
    records.append({"name": "opencode", "pid": proc.pid})
    (state / "processes.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )
    # The preview app resolves credentials at point of use. A private environment
    # file used by its existing launcher is updated separately before restart.
    print(
        json.dumps(
            {"pid": proc.pid, "port": 18817, "image_id": image_id, "submitted_turns": 0}
        )
    )


if __name__ == "__main__":
    main()
