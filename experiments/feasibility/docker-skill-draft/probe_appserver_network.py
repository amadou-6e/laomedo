"""Credential-free network denial through the Docker runner's app-server path."""

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
    source = Path(__file__).resolve().parent
    args = docker_prefix(draft, canonical, store)
    args[args.index("--workdir"):args.index("--workdir")] = [
        "--mount", f"type=bind,source={source},target=/probe,readonly"]
    docker = Path(shutil.which("docker") or "").resolve(strict=True)
    report = {"model_calls": 0, "docker_network": "bridge",
              "runner_permission_profile": "container-edit"}
    server = AppServer(docker, draft, os.environ.copy(), state,
                       startup_args=args)
    try:
        report["initialized"] = server.initialize()[0]
        if not report["initialized"]:
            return
        response = server.send("command/exec", {
            "command": ["node", "/probe/connect.js", "chatgpt.com", "443"],
            "cwd": "/draft", "timeoutMs": 15000,
        }, timeout=25)
        result = response.get("result") or {}
        combined = str(result.get("stdout") or "") + str(result.get("stderr") or "")
        report["command_response"] = "result" in response
        report["exit_code"] = result.get("exitCode")
        report["command_started"] = "started" in combined
        report["connection_succeeded"] = "connected" in combined
        report["deny_class"] = (
            "EPERM" if "EPERM" in combined else
            "EAI_AGAIN" if "EAI_AGAIN" in combined else
            "other_or_unreported")
        report["result_keys"] = sorted(result)
        report["boundary_passed"] = (
            report["command_response"]
            and report["exit_code"] not in (None, 0)
            and report["command_started"]
            and not report["connection_succeeded"]
            and report["deny_class"] in ("EPERM", "EAI_AGAIN"))
    finally:
        report["server_status"] = server.close()
        (root / "summary.json").write_text(json.dumps(report, indent=2),
                                           encoding="utf-8")
        print(json.dumps(report, indent=2))
    if not report.get("boundary_passed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
