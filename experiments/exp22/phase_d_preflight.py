"""Credential-free installed-Langflow graph Stop preflight for Phase D."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
IMAGE = ("langflowai/langflow@sha256:"
         "34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0")


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait(path, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(.05)
    raise RuntimeError("preflight_wait_timeout")


def _journal(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    state = args.state.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (state, *state.parents)):
        parser.error("state_must_be_outside_git")
    if state.exists() and any(state.iterdir()):
        parser.error("state_must_be_empty")
    state.mkdir(parents=True, exist_ok=True)
    runner_state = state / "fake-runner"
    runner_state.mkdir()
    graph_state = state / "graph"
    graph_state.mkdir()
    (graph_state / "task.txt").write_text("CASE_B synthetic stop probe", encoding="utf-8")
    port = _port()
    name = "laomedo-phase-d-preflight-" + uuid4().hex[:16]
    fake_log = (state / "fake-runner.log").open("w", encoding="utf-8")
    child_log = (state / "graph.log").open("w", encoding="utf-8")
    fake = subprocess.Popen([sys.executable, "-m", "experiments.exp94.fake_runner",
                             "--state", str(runner_state), "--port", str(port)],
                            cwd=ROOT, stdout=fake_log, stderr=subprocess.STDOUT)
    child = None
    try:
        _wait(runner_state / "api-token", 8)
        command = ["docker", "run", "--rm", "--pull=never", "--name", name,
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
                   "--mount", f"type=bind,source={graph_state},target=/state",
                   "--mount", (f"type=bind,source={runner_state / 'api-token'},"
                               "target=/run/secrets/laomedo-runner-token,readonly"),
                   "-e", "PYTHONPATH=/workspace", "--entrypoint", "python", IMAGE,
                   "/workspace/experiments/exp22/phase_d_graph.py", "--state", "/state",
                   "--runner-port", str(port), "--skill-id", "laomedo-pilot",
                   "--revision-id", "sha256:" + "a" * 64]
        child = subprocess.Popen(command, cwd=ROOT, stdout=child_log,
                                 stderr=subprocess.STDOUT)
        journal_path = runner_state / "journal.jsonl"
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if any(row.get("kind") == "synthetic_wait_started" for row in
                   _journal(journal_path)):
                break
            if child.poll() is not None:
                raise RuntimeError("graph_exited_before_wait")
            time.sleep(.1)
        else:
            raise RuntimeError("synthetic_wait_missing")
        (graph_state / "stop.signal").write_text("stop", encoding="ascii")
        child.wait(timeout=35)
        rows = _journal(journal_path)
        kinds = [row.get("kind") for row in rows]
        starts = [row for row in rows if row.get("kind") == "post_received"]
        cancels = [row for row in rows if row.get("kind") == "cancel_received"]
        lookups = [row for row in rows if row.get("kind") == "request_lookup"]
        result = json.loads((graph_state / "graph-result.json").read_text(encoding="utf-8"))
        child_log.flush()
        token = (runner_state / "api-token").read_text(encoding="ascii").strip()
        token_in_graph_output = any(token in path.read_text(encoding="utf-8", errors="replace")
                                    for path in (state / "graph.log",
                                                 graph_state / "graph-result.json"))
        passed = (child.returncode == 0 and result["stop_signal_seen"] and
                  result["graph_outcome"] == "cancelled" and len(starts) == 1 and
                  len(cancels) == 1 and len(lookups) == 1 and
                  starts[0]["run_id"] == cancels[0]["run_id"] == lookups[0]["run_id"] and
                  "synthetic_effect" not in kinds and not token_in_graph_output)
        summary = {"provider_login_mounted": False, "runner_api_token_mounted": True,
                   "model_turn_submitted": False,
                   "passed": passed, "starts": len(starts), "lookups": len(lookups),
                   "cancels": len(cancels), "late_effects": kinds.count("synthetic_effect"),
                   "runner_token_in_graph_output": token_in_graph_output,
                   "graph_outcome": result["graph_outcome"]}
        (state / "sanitized.json").write_text(json.dumps(summary, indent=2),
                                               encoding="utf-8")
        print(json.dumps(summary))
        if not passed:
            raise RuntimeError("phase_d_preflight_failed")
    finally:
        if child and child.poll() is None:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           timeout=20)
            child.wait(timeout=20)
        fake.terminate()
        fake.wait(timeout=10)
        child_log.close()
        fake_log.close()


if __name__ == "__main__":
    main()
