"""Launch task-owned normal services; no model budget or fixture provider."""

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
    if (state / "processes.json").exists():
        raise SystemExit(
            "Existing task services retained; reconcile before another launch."
        )
    for port in [17863, 18815, 18816]:
        with socket.socket() as check:
            check.bind(("127.0.0.1", port))
    source = root / ".tools/agent-refactor-205"
    python = "C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(source / "src")
    env["LAOMEDO_AGENT_ACTIVITY_DB"] = str(state / "activity.db")
    records = []

    def start(name, arguments, extra=None):
        with (state / (name + ".log")).open("wb") as output:
            process = subprocess.Popen(
                [python, *arguments],
                cwd=source,
                env=env | (extra or {}),
                stdout=output,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        records.append({"name": name, "pid": process.pid})
        (state / "processes.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8"
        )

    start(
        "lease",
        [
            "-m",
            "laomedo.host.leases.service_cli",
            "serve",
            "--state",
            str(state / "lease"),
        ],
    )
    start(
        "codex",
        [
            "-m",
            "laomedo.agents.agents.codex.cli",
            "--state",
            str(state / "codex"),
            "--skill-store",
            str(state / "registry"),
            "--source-workspace",
            str(state / "workspace/content"),
            "--lease-service",
            str(state / "lease"),
            "--port",
            "18815",
        ],
    )
    start(
        "claude",
        [
            "-m",
            "laomedo.agents.agents.claude.cli",
            "--state",
            str(state / "claude"),
            "--skill-store",
            str(state / "registry"),
            "--source",
            str(state / "workspace/content"),
            "--lease-service",
            str(state / "lease"),
            "--port",
            "18816",
        ],
        {
            "LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN": "1",
            "LAOMEDO_CLAUDE_LOGIN_STATE_DIR": str(state / "claude-login"),
        },
    )
    app = state / "app.py"
    app.write_text(
        'import os,laomedo,uvicorn\nlaomedo.__path__.append(os.environ["LAOMEDO_COMPONENT_DIR"])\nuvicorn.run("laomedo.integrations.langflow.viewer:create_app",factory=True,host="127.0.0.1",port=17863)\n',
        encoding="utf-8",
    )
    frontend = Path(
        json.loads((evidence / "frontend-path.json").read_text(encoding="utf-8"))[
            "path"
        ]
    )
    start(
        "app",
        [str(app)],
        {
            "LANGFLOW_CONFIG_DIR": str(state / "langflow"),
            "LFX_CONFIG_DIR": str(state / "langflow"),
            "LANGFLOW_DATABASE_URL": "sqlite:///"
            + (state / "langflow/flow.db").as_posix(),
            "LANGFLOW_FRONTEND_PATH": str(frontend / "build"),
            "LANGFLOW_AUTO_LOGIN": "true",
            "DO_NOT_TRACK": "true",
            "LANGFLOW_COMPONENTS_PATH": str(source / "components"),
            "LAOMEDO_COMPONENT_DIR": str(source / "components/laomedo"),
            "LAOMEDO_SKILL_STORE": str(state / "registry"),
            "LAOMEDO_RUNNER_TOKEN_FILE": str(state / "codex/api-token"),
            "LAOMEDO_CODEX_RUNNER_TOKEN_FILE": str(state / "codex/api-token"),
            "LAOMEDO_CLAUDE_RUNNER_TOKEN_FILE": str(state / "claude/api-token"),
        },
    )
    print(json.dumps(records))


if __name__ == "__main__":
    main()
