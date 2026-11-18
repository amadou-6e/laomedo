"""Run harmless native Claude/OpenCode graph checks in the existing Activity preview."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import time
import requests

ROOT = Path("C:/CodeWorkspace/laomedo")
APP = ROOT / ".tools/worktrees/assistant-291"
EXP = Path(__file__).resolve().parents[1]
META = json.loads((ROOT / ".tools/assistant-291-live.json").read_text(encoding="utf-8"))
sys.path.insert(0, str(APP / "src"))
os.environ.update(
    PYTHONPATH=str(APP / "src"),
    LAOMEDO_AGENT_ACTIVITY_DB=str(Path(META["state"]) / "activity.db"),
    LAOMEDO_RUNNER_OTEL="1",
)

TASK = """Review this small disposable task-board workspace using real tool calls. Read README.md, requirements.md and tasks.json separately. Send a short progress message before each read and report what you learned after it. Then count the task statuses using one read-only command. Do not edit files, delegate, access credentials or use network tools. Finish with about 350 words: a summary grounded in those files, a Markdown table comparing bounded and expanding transcripts, a TypeScript task-status type in a fenced code block, and a short checklist. Explain that missing telemetry is unknown rather than zero. This is a real activity UI check, not a simulated conversation."""


def main(provider):
    import langflow
    from lfx.services.manager import get_service_manager
    from lfx.services.schema import ServiceType
    from lfx.services.settings.service import SettingsService
    from lfx.services.settings.base import Settings
    from lfx.services.settings.auth import AuthSettings
    from lfx.graph.graph.base import Graph
    from laomedo.host.runner.http.server import RunnerServer

    state = Path(META["state"]) / (
        "activity-295-real-" + provider + "-" + str(int(time.time()))
    )
    state.mkdir(parents=True)
    config = str(state / "config")
    Path(config).mkdir()
    get_service_manager().services[ServiceType.SETTINGS_SERVICE] = SettingsService(
        Settings(config_dir=config), AuthSettings(CONFIG_DIR=config)
    )
    source = state / "repository/source"
    source.mkdir(parents=True)
    (source / "README.md").write_text(
        "# Activity task board\nA task has a title, status and owner. Compare bounded and expanding transcripts.\n",
        encoding="utf-8",
    )
    (source / "requirements.md").write_text(
        "Keep graph execution context visible. Render Markdown tables, code and tool output. Preserve source inspection. Never invent missing usage or telemetry.\n",
        encoding="utf-8",
    )
    (source / "tasks.json").write_text(
        json.dumps(
            [
                {"title": "Review hierarchy", "status": "done", "owner": "design"},
                {
                    "title": "Inspect conversation",
                    "status": "in_progress",
                    "owner": "owner",
                },
                {"title": "Check telemetry", "status": "todo", "owner": "engineering"},
            ]
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
    lease = state / "lease"
    log = (state / "lease.log").open("wb")
    supervisor = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "laomedo.host.leases.service_cli",
            "serve",
            "--state",
            str(lease),
        ],
        env=dict(os.environ),
        stdout=log,
        stderr=log,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    server = None
    profile_volume = None
    temporary = tempfile.TemporaryDirectory(prefix="laomedo-activity-provider-")
    try:
        until = time.monotonic() + 30
        while not (lease / "service.json").exists():
            if supervisor.poll() is not None or time.monotonic() > until:
                raise RuntimeError("lease_start_failed")
            time.sleep(0.1)
        if provider == "claude":
            from laomedo.agents.agents.claude.agent import ClaudeAgent

            os.environ["LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN"] = "1"
            profile_volume = (
                "laomedo-claude-activity-295-" + state.name.rsplit("-", 1)[-1]
            )
            agent = ClaudeAgent(
                state / "runner",
                state / "registry",
                source,
                lease_service=lease,
                profile_volume=profile_volume,
            )
        else:
            from laomedo.agents.agents.opencode.agent import OpenCodeAgent
            from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime

            helper = runpy.run_path(
                str(EXP / "provider-205-integration/opencode_profile.py")
            )
            profile = Path(temporary.name) / "profile"
            helper["prepare_profile"](profile)

            def transport_factory(workspace, evidence):
                return OpenCodeAgentRuntime(workspace, evidence, profile=profile)

            agent = OpenCodeAgent(
                state / "runner",
                state / "registry",
                source,
                transport_factory=transport_factory,
                lease_service=lease,
            )
        ready = agent.readiness()
        print(
            json.dumps(
                {
                    "stage": "readiness",
                    "provider": provider,
                    "ready": ready.ready,
                    "reason": ready.reason,
                }
            ),
            flush=True,
        )
        if ready.ready is False:
            return
        catalogue = agent.catalog.list_models()
        candidates = catalogue.models
        selected = next(
            (
                m
                for m in candidates
                if (provider == "claude" and m.id == "sonnet")
                or (provider == "opencode" and "haiku" in m.id)
            ),
            candidates[0],
        )
        effort = (
            "default"
            if provider == "opencode"
            else "low" if "low" in selected.reasoning_efforts else "default"
        )
        print(
            json.dumps({"stage": "model", "provider": provider, "model": selected.id}),
            flush=True,
        )
        server = RunnerServer(agent, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        os.environ["LAOMEDO_RUNNER_TOKEN_FILE"] = str(agent.state / "api-token")
        os.environ["LAOMEDO_" + provider.upper() + "_RUNNER_TOKEN_FILE"] = str(
            agent.state / "api-token"
        )
        build = runpy.run_path(str(APP / "examples/agents/build_flow.py"))["build"]
        flow = build(
            provider=provider,
            model=selected.id,
            effort=effort,
            runner_url="http://127.0.0.1:" + str(server.server_port),
            task=TASK,
        )
        flow["name"] = provider.title() + " activity review - real run"
        flow["description"] = (
            "Actual native provider execution in an isolated harmless workspace. No synthetic conversation or telemetry."
        )
        session = requests.Session()
        session.headers["Authorization"] = (
            "Bearer "
            + session.get(META["base"] + "/api/v1/auto_login", timeout=30).json()[
                "access_token"
            ]
        )
        response = session.post(META["base"] + "/api/v1/flows/", json=flow, timeout=60)
        response.raise_for_status()
        saved = response.json()
        (ROOT / ".tools" / ("activity-295-real-" + provider + ".json")).write_text(
            json.dumps(
                {"flow": saved["id"], "provider": provider, "state": str(state)}
            ),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"stage": "graph_start", "provider": provider, "flow": saved["id"]}
            ),
            flush=True,
        )
        graph = Graph.from_payload(saved, flow_id=saved["id"], user_id=saved["user_id"])
        asyncio.run(graph.arun(inputs=[{}], outputs=["agent"]))
        time.sleep(3)
        response = session.get(
            META["base"] + "/api/v1/laomedo/agent-executions/" + saved["id"], timeout=30
        )
        response.raise_for_status()
        runs = response.json()["runs"]
        print(
            json.dumps(
                {
                    "stage": "graph_settled",
                    "provider": provider,
                    "flow": saved["id"],
                    "runs": [
                        {"status": r["status"], "stream_state": r.get("stream_state")}
                        for r in runs
                    ],
                }
            ),
            flush=True,
        )
    finally:
        if server:
            server.shutdown()
            server.server_close()
        supervisor.terminate()
        supervisor.wait(timeout=20)
        log.close()
        temporary.cleanup()
        if profile_volume:
            removed = subprocess.run(
                ["docker", "volume", "rm", profile_volume],
                capture_output=True,
                timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            print(
                json.dumps(
                    {"stage": "own_profile_cleanup", "removed": removed.returncode == 0}
                ),
                flush=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("provider", choices=["claude", "opencode"])
    args = parser.parse_args()
    try:
        main(args.provider)
    except Exception as error:
        import traceback

        print(
            json.dumps(
                {
                    "stage": "blocked",
                    "provider": args.provider,
                    "error_type": type(error).__name__,
                    "code": getattr(error, "code", None),
                    "frames": [
                        {
                            "file": Path(f.filename).name,
                            "line": f.lineno,
                            "function": f.name,
                        }
                        for f in traceback.extract_tb(error.__traceback__)
                    ],
                }
            ),
            flush=True,
        )
        raise SystemExit(1)
