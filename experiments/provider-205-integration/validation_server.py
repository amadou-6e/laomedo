"""Launch an isolated, runnable Codex graph for interactive human validation."""

import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse

REPO = Path("C:/CodeWorkspace/laomedo")


def main():
    metadata_path = (
        REPO
        / ".tools/review/provider-composition/develop-integration/interactive-validation.json"
    )
    previous = (
        json.loads(metadata_path.read_text(encoding="utf-8"))
        if "--resume" in sys.argv
        else None
    )
    root = (
        Path(previous["state"])
        if previous
        else Path(tempfile.mkdtemp(prefix="laomedo-interactive-validation-"))
    )
    config = root / "langflow"
    config.mkdir(exist_ok=True)
    registry = root / "registry"
    registry.mkdir(exist_ok=True)
    os.environ.update(
        {
            "PYTHONPATH": str(REPO / "src"),
            "LANGFLOW_CONFIG_DIR": str(config),
            "LFX_CONFIG_DIR": str(config),
            "LANGFLOW_DATABASE_URL": "sqlite:///" + (config / "flow.db").as_posix(),
            "LANGFLOW_FRONTEND_PATH": str(
                REPO / ".tools/275/provider-integration-upstream/src/frontend/build"
            ),
            "LANGFLOW_COMPONENTS_PATH": str(REPO / "components"),
            "LAOMEDO_COMPONENT_DIR": str(REPO / "components/laomedo"),
            "LANGFLOW_AUTO_LOGIN": "true",
            "LANGFLOW_DO_NOT_TRACK": "true",
            "LAOMEDO_SKILL_STORE": str(registry),
            "LAOMEDO_AGENT_ACTIVITY_DB": str(root / "activity.db"),
        }
    )
    sys.path.insert(0, str(REPO / "src"))
    source = root / "repository/source"
    source.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
    (source / "task.txt").write_text(
        "Validation marker: amber-205.\n", encoding="utf-8"
    )
    lease = root / "lease"
    log = (root / "lease.log").open("wb")
    supervisor = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "laomedo.host.leases.service_cli",
            "serve",
            "--state",
            str(lease),
        ],
        stdout=log,
        stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    runner = None
    agent = None
    try:
        deadline = time.monotonic() + 30
        while not (lease / "service.json").exists():
            if supervisor.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError("lease_service_unavailable")
            time.sleep(0.1)
        from laomedo.agents.agents.codex.agent import CodexAgent
        from laomedo.host.runner.http.server import RunnerServer

        native = runpy.run_path(
            str(
                REPO
                / ".tools/worktrees/docker-acceptance-exp/experiments/docker-boundary-277/acceptance.py"
            )
        )
        agent = CodexAgent(
            root / "runner",
            registry,
            source,
            lease_service=lease,
            **native["session_login"](),
        )
        runner = RunnerServer(
            agent, port=urlparse(previous["runner_url"]).port if previous else 0
        )
        threading.Thread(target=runner.serve_forever, daemon=True).start()
        os.environ["LAOMEDO_RUNNER_TOKEN_FILE"] = str(agent.state / "api-token")
        catalogue = agent.catalog.list_models()
        selected = next(
            (model for model in catalogue.models if model.id == "gpt-6-luna"),
            catalogue.models[0],
        )
        efforts = selected.reasoning_efforts
        effort = "low" if "low" in efforts else (efforts[0] if efforts else "default")
        build = runpy.run_path(str(REPO / "examples/agents/build_flow.py"))["build"]
        flow = build(
            provider="codex",
            model=selected.id,
            effort=effort,
            runner_url="http://127.0.0.1:" + str(runner.server_port),
            task="Read task.txt and reply only with its validation marker. Do not edit files or delegate.",
            workflow="resume",
            follow_up="What validation marker did you just read? Reply only with it, without tools or delegation.",
        )
        flow["name"] = "Codex validation - fresh and resume"
        flow["description"] = (
            "Runnable validation on the current branch. Run the graph to check fresh/resume and retained Activity. Opening this graph does not submit a task."
        )
        for node in flow["data"]["nodes"]:
            template = node["data"]["node"]["template"]
            template["model"]["options"] = [model.id for model in catalogue.models]
            template["effort"]["options"] = list(selected.reasoning_efforts)
        graph_path = root / "validation-graph.json"
        graph_path.write_text(json.dumps(flow, ensure_ascii=False), encoding="utf-8")
        metadata = {
            "base": "http://127.0.0.1:17876",
            "graph_file": str(graph_path),
            "state": str(root),
            "runner_url": "http://127.0.0.1:" + str(runner.server_port),
            "model": selected.id,
            "revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
            ).strip(),
            "executed": False,
        }
        (
            REPO
            / ".tools/review/provider-composition/develop-integration/interactive-validation.json"
        ).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        import laomedo
        import uvicorn

        laomedo.__path__.append(str(REPO / "components/laomedo"))
        os.chdir(root)
        print(
            json.dumps(
                {
                    "stage": "validation_ready",
                    "base": metadata["base"],
                    "model": selected.id,
                    "executed": False,
                }
            ),
            flush=True,
        )
        uvicorn.run(
            "laomedo.integrations.langflow.viewer:create_app",
            factory=True,
            host="127.0.0.1",
            port=17876,
        )
    finally:
        if agent is not None:
            for path in (agent.state / "runs").glob("*/record.json"):
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("status") in {"running", "queued", "starting"}:
                    agent.cancel(record["run_id"])
        if runner is not None:
            runner.shutdown()
            runner.server_close()
        supervisor.terminate()
        supervisor.wait(timeout=20)
        log.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        import traceback

        print(
            json.dumps(
                {
                    "frames": [
                        {
                            "file": Path(frame.filename).name,
                            "line": frame.lineno,
                            "function": frame.name,
                        }
                        for frame in traceback.extract_tb(error.__traceback__)
                    ]
                }
            ),
            flush=True,
        )
        print(
            json.dumps(
                {
                    "stage": "validation_start_failed",
                    "type": type(error).__name__,
                    "code": getattr(error, "code", None),
                }
            ),
            flush=True,
        )
        raise SystemExit(1)
