"""Independent real graph recovery preview; does not touch the owner's graphs."""

import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path

from laomedo.agents.agents.codex.agent import CodexAgent


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    source = root / ".tools/agent-refactor-205"
    e = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((e / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    for port in [17864, 18825]:
        with socket.socket() as check:
            check.bind(("127.0.0.1", port))
    private = state / "recovery-preview"
    if private.exists():
        raise SystemExit("Existing recovery preview retained; reconcile first.")
    # Production constructor admits the dedicated state and API token without
    # opening a listener or dispatching a turn.
    agent = CodexAgent(
        private / "runner",
        state / "registry",
        state / "workspace/content",
        lease_service=state / "lease",
    )
    config = {
        "provider": "codex",
        "state": str(private / "runner"),
        "skill_store": str(state / "registry"),
        "source": str(state / "workspace/content"),
        "lease_service": str(state / "lease"),
        "port": 18825,
    }
    (private / "service.json").write_text(json.dumps(config), encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "maintained_agents", source / "examples/agents/build_flow.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    catalog = json.loads((state / "codex-catalog.json").read_text(encoding="utf-8"))
    selected = next(m for m in catalog["models"] if m["id"] == "gpt-6-luna")
    flow = module.build(
        provider="codex",
        model=selected["id"],
        effort="low",
        runner_url="http://127.0.0.1:18825",
        task="Read README.md and summarize it. Do not modify files or delegate.",
    )
    flow["name"] = "Agent recovery - PR250 isolated real validation"
    flow["data"]["nodes"][0]["data"]["node"]["template"]["model"]["options"] = [
        m["id"] for m in catalog["models"]
    ]
    flow["data"]["nodes"][0]["data"]["node"]["template"]["effort"]["options"] = (
        selected["efforts"]
    )
    (private / "flow.json").write_text(json.dumps(flow), encoding="utf-8")
    app = private / "app.py"
    app.write_text(
        'import laomedo,os,uvicorn\nlaomedo.__path__.append(os.environ["LAOMEDO_COMPONENT_DIR"])\nuvicorn.run("laomedo.integrations.langflow.viewer:create_app",factory=True,host="127.0.0.1",port=17864)\n',
        encoding="utf-8",
    )
    frontend = Path(
        json.loads((e / "frontend-path.json").read_text(encoding="utf-8"))["path"]
    )
    env = os.environ | {
        "PYTHONPATH": str(source / "src"),
        "LAOMEDO_AGENT_ACTIVITY_DB": str(private / "activity.db"),
        "LAOMEDO_RUNNER_SERVICE_FILE": str(private / "service.json"),
        "LANGFLOW_CONFIG_DIR": str(private / "langflow"),
        "LFX_CONFIG_DIR": str(private / "langflow"),
        "LANGFLOW_DATABASE_URL": "sqlite:///"
        + (private / "langflow/flow.db").as_posix(),
        "LANGFLOW_FRONTEND_PATH": str(frontend / "build"),
        "LANGFLOW_AUTO_LOGIN": "true",
        "DO_NOT_TRACK": "true",
        "LANGFLOW_COMPONENTS_PATH": str(source / "components"),
        "LAOMEDO_COMPONENT_DIR": str(source / "components/laomedo"),
        "LAOMEDO_SKILL_STORE": str(state / "registry"),
        "LAOMEDO_RUNNER_TOKEN_FILE": str(private / "runner/api-token"),
        "LAOMEDO_CODEX_RUNNER_TOKEN_FILE": str(private / "runner/api-token"),
    }
    with (private / "app.log").open("wb") as log:
        process = subprocess.Popen(
            [
                "C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe",
                str(app),
            ],
            cwd=source,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    (private / "process.json").write_text(
        json.dumps({"pid": process.pid, "app_port": 17864, "runner_port": 18825}),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "app_pid": process.pid,
                "app_port": 17864,
                "runner_port": 18825,
                "submitted_turns": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
