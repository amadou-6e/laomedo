"""Bounded, single-use Phase C model probe using only synthetic GitHub effects.

No real GitHub credential or provider write enters this process. State and raw
events must be placed in a private directory outside every Git worktree.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from laomedo.local_runner import IMAGE, VOLUME
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.skill_store import SkillStore


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "exp22" / "phase-c-source"
SKILL = ROOT / "experiments" / "exp22" / "phase-c-skill"
TASKS = ROOT / "experiments" / "exp22" / "PHASE-C-TASKS.md"
PROTOCOL = ROOT / "experiments" / "exp22" / "PHASE-C-PROTOCOL.md"
MODEL = "gpt-6-luna"
EFFORT = "low"
TURN_CAP = 4


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _wait(path: Path, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(.05)
    raise RuntimeError("service_start_timeout")


def _private_empty(path: Path) -> Path:
    path = path.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise RuntimeError("state_must_be_outside_git")
    if path.exists() and any(path.iterdir()):
        raise RuntimeError("state_must_be_empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _request(port: int, token: str, method: str, path: str,
             body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = Request(f"http://127.0.0.1:{port}{path}", data=data,
                  method=method, headers={"Authorization": "Bearer " + token,
                                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=12) as response:
            return json.load(response)
    except HTTPError as error:
        return json.load(error)


def _events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    return events


def _journal(path: Path) -> list[dict]:
    return _events(path)


def _wait_run(port, token, run_id, predicate, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        status = _request(port, token, "GET", "/v1/runs/" + run_id)
        if predicate(status):
            return status
        time.sleep(.1)
    raise RuntimeError("run_observation_timeout")


def _is_long_command(event):
    item = (event.get("params") or {}).get("item") or {}
    return (event.get("method") == "item/started" and
            item.get("type") == "commandExecution" and
            "sleep 30" in str(item.get("command", "")))


def _stop(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--allow-one-model-turn", action="store_true")
    args = parser.parse_args()
    if not args.allow_one_model_turn:
        parser.error("explicit_one_turn_execution_flag_required")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT, text=True)
    if dirty.strip():
        parser.error("reviewed_source_must_be_committed_and_clean")
    state = _private_empty(args.state)
    runner_state, service_state = state / "runner", state / "service"
    runs = runner_state / "runs"
    runs.mkdir(parents=True)
    service_state.mkdir()
    authority = RunGrantAuthority(service_state / "authority.sqlite")
    skill = SkillStore(state / "skills").import_skill("phase-c-boundary", SKILL)
    pins = {"protocol": _digest(PROTOCOL), "task": _digest(TASKS),
            "skill": _digest(SKILL / "SKILL.md"),
            "source": _digest(SOURCE / "mediation-loop.mjs"),
            "client": _digest(ROOT / "laomedo" / "file_mediation_client.mjs"),
            "bridge": _digest(ROOT / "laomedo" / "file_mediation_bridge.py"),
            "implementation": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "model": MODEL, "effort": EFFORT, "turn_cap": TURN_CAP,
            "turns_before": 0}
    (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
    host_log = (state / "host.log").open("w", encoding="utf-8")
    runner_log = (state / "runner.log").open("w", encoding="utf-8")
    host = subprocess.Popen([
        sys.executable, "-m", "experiments.exp22.phase_c_fake_host",
        "--state", str(service_state), "--runner-runs-root", str(runs)],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=host_log,
        stderr=subprocess.STDOUT,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
    runner = None
    try:
        _wait(service_state / "lease" / "service.json", 8)
        _wait(service_state / "mediator" / "file-bridge.json", 8)
        auth_check = subprocess.run([
            "docker", "run", "--rm", "--pull=never", "--network", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", "10001:10001", "--mount",
            f"type=volume,source={VOLUME},target=/home/runner/.codex,readonly",
            IMAGE, "sh", "-c", "test -f /home/runner/.codex/auth.json"],
            capture_output=True, timeout=15)
        if auth_check.returncode != 0:
            raise RuntimeError("private_login_copy_absent")
        port = _port()
        runner = subprocess.Popen([
            sys.executable, "-m", "laomedo.local_runner",
            "--state", str(runner_state), "--skill-store", str(state / "skills"),
            "--source-workspace", str(SOURCE), "--port", str(port),
            "--max-model-turns", str(TURN_CAP),
            "--lease-service", str(service_state / "lease"),
            "--github-authority-store", str(service_state / "authority.sqlite"),
            "--mediator-state", str(service_state / "mediator"),
            "--file-mediation"], cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=runner_log, stderr=subprocess.STDOUT,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
        _wait(runner_state / "api-token", 8)
        api_token = (runner_state / "api-token").read_text(encoding="utf-8")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                _request(port, api_token, "GET", "/v1/runs/" + str(uuid4()))
                break
            except (OSError, URLError):
                time.sleep(.05)
        else:
            raise RuntimeError("runner_start_timeout")

        # Phase A. The request ID and grant ref are consumed once. A timeout
        # does not permit replay with another effect ID.
        reference_a = authority.approve(
            invocation_id="phase-c-a-" + uuid4().hex,
            repository="example/disposable", branch="phase-c-a",
            operations={"pr_update"}, target_prs={7: "main"},
            reviewed_by="bounded-local-phase-c")
        prompt_a = TASKS.read_text(encoding="utf-8").split("## Active cancellation", 1)[1].split(
            "## Runner-tree kill", 1)[0].split("The host observes", 1)[0].strip()
        body = {"request_id": str(uuid4()), "task": prompt_a,
                "model": MODEL, "effort": EFFORT,
                "skill_ref": {"skill_id": "phase-c-boundary",
                              "revision_id": skill["revision_id"],
                              "tree_hash": skill["revision_id"]},
                "github_authorization_ref": reference_a}
        active = _request(port, api_token, "POST", "/v1/runs/async", body)
        run_a = active.get("run_id")
        if not run_a:
            raise RuntimeError("active_run_ack_missing")
        event_path = runs / run_a / "raw-events.jsonl"
        journal_path = service_state / "mediator" / "file-bridge-journal.jsonl"
        start = time.monotonic()
        long_started = False
        while time.monotonic() - start < 90:
            if any(_is_long_command(event) for event in _events(event_path)):
                long_started = True
                break
            status = _request(port, api_token, "GET", "/v1/runs/" + run_a)
            if status.get("status") not in {"prepared", "running"}:
                break
            time.sleep(.1)
        if not long_started:
            raise RuntimeError("active_long_command_not_seen")
        long_started_at = time.monotonic()
        cancel = _request(port, api_token, "POST", f"/v1/runs/{run_a}/cancel", {})
        final_a = _wait_run(port, api_token, run_a,
                            lambda x: x.get("status") not in {"prepared", "running"}, 30)
        a_effects = [item for item in _journal(journal_path) if
                     item.get("run_id") == run_a]
        active_result = {"run_id": run_a, "ack_status": active.get("status"),
                         "cancel_ack": cancel.get("status"),
                         "status": final_a.get("status"),
                         "cancel_confirmed": final_a.get("cancel_confirmed"),
                         "native_statuses": [e.get("params", {}).get("turn", {}).get("status")
                                             for e in _events(event_path)
                                             if e.get("method") == "turn/completed"],
                         "fake_effects": a_effects,
                         "raw_event_sha256": _digest(event_path)}
        if time.monotonic() < long_started_at + 31:
            time.sleep(long_started_at + 31 - time.monotonic())
        active_result["sentinel_present_after_delay"] = (
            runs / run_a / "workspace" / "cancel-marker.txt").exists()
        name = (final_a.get("container_ownership") or {}).get("name")
        inspected = subprocess.run(["docker", "inspect", name],
                                   capture_output=True, timeout=12) if name else None
        active_result["container_absent"] = bool(
            inspected is not None and inspected.returncode == 1)
        active_result["host_survived"] = host.poll() is None
        (state / "active-sanitized.json").write_text(
            json.dumps(active_result, indent=2), encoding="utf-8")
        if (final_a.get("status") != "cancelled" or
                not final_a.get("cancel_confirmed") or
                "interrupted" not in active_result["native_statuses"] or
                not any(e.get("state") == "confirmed" for e in a_effects) or
                active_result["sentinel_present_after_delay"] or
                not active_result["container_absent"] or
                not active_result["host_survived"]):
            raise RuntimeError("active_case_not_passed_no_kill_turn")

        # Phase B is deliberately not auto-dispatched here. The host must
        # inspect A's private trace and grant journal before spending turn 2.
        print(json.dumps({"active": "passed", "run_id": run_a,
                          "turns_used": 1, "kill_case": "not_started"}))
    finally:
        if runner is not None:
            _stop(runner)
        _stop(host)
        host_log.close()
        runner_log.close()


if __name__ == "__main__":
    main()
