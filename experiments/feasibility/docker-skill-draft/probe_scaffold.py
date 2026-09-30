"""Find when Docker app-server creates empty workspace scaffolding, no model turn."""

import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "120"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "122"))
from _shared import AppServer
from probe_container_agent_edit import docker_prefix
from probe_draft_guards import BASE_SKILL


def names(path: Path) -> list[str]:
    return sorted(child.name for child in path.iterdir())


def main() -> None:
    state = (Path(os.environ["LOCALAPPDATA"]) / "Laomedo" /
             "feasibility-120" / "issue-122-docker").resolve(strict=True)
    root = state / "diagnostics" / str(uuid4())
    draft, canonical, store = (root / name for name in
                               ("draft", "canonical", "store"))
    for path in (draft, canonical, store):
        path.mkdir(parents=True)
    (draft / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
    (canonical / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
    (store / "sentinel.txt").write_text("STORE-ORIGINAL", encoding="utf-8")
    report = {"model_calls": 0, "before": names(draft)}
    docker = Path(shutil.which("docker") or "").resolve(strict=True)
    server = AppServer(docker, draft, os.environ.copy(), state,
                       startup_args=docker_prefix(draft, canonical, store))
    try:
        report["initialized"] = server.initialize()[0]
        report["after_initialize"] = names(draft)
        command = server.send("command/exec", {
            "command": ["sh", "-c", "printf canary > /draft/canary.txt"],
            "cwd": "/draft", "timeoutMs": 10000,
        }, timeout=20)
        report["command_exit"] = (command.get("result") or {}).get("exitCode")
        report["after_command"] = names(draft)
        started = server.send("thread/start", {
            "model": "gpt-6-luna", "cwd": "/draft", "approvalPolicy": "never",
        }, timeout=20)
        report["thread_started"] = "result" in started
        report["after_thread_start"] = names(draft)
    finally:
        report["server_status"] = server.close()
        (root / "summary.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
