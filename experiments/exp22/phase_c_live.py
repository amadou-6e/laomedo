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
from laomedo.container_lease import cleanup_exact, inspect_exact
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.skill_store import SkillStore


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "exp22" / "phase-c-source"
SKILL = ROOT / "experiments" / "exp22" / "phase-c-skill"
TASKS = ROOT / "experiments" / "exp22" / "PHASE-C-TASKS.md"
PROMPT_A = ROOT / "experiments" / "exp22" / "phase-c-prompt-a.txt"
PROTOCOL = ROOT / "experiments" / "exp22" / "PHASE-C-PROTOCOL.md"
MODEL = "gpt-6-luna"
EFFORT = "low"
TURN_CAP = 4
BUDGET = Path.home() / "AppData" / "Local" / "Laomedo" / "exp22-phase-c-turns.json"


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


def _budget_update(*, attempt_id=None, result=None, state=None):
    """Reserve before HTTP submission; a timeout still spends one turn."""
    BUDGET.parent.mkdir(parents=True, exist_ok=True)
    lock = BUDGET.with_suffix(".lock")
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise RuntimeError("phase_c_budget_locked") from None
    os.close(descriptor)
    try:
        value = (json.loads(BUDGET.read_text(encoding="utf-8")) if BUDGET.exists()
                 else {"cap": TURN_CAP, "attempts": []})
        if value.get("cap") != TURN_CAP or not isinstance(value.get("attempts"), list):
            raise RuntimeError("phase_c_budget_invalid")
        if attempt_id is None:
            if len(value["attempts"]) >= TURN_CAP:
                raise RuntimeError("phase_c_budget_exhausted")
            attempt_id = uuid4().hex
            value["attempts"].append({"id": attempt_id, "state_dir": str(state),
                                      "submitted_at": time.time(),
                                      "result": "submitted_unknown"})
        else:
            matches = [entry for entry in value["attempts"] if
                       entry.get("id") == attempt_id]
            if len(matches) != 1:
                raise RuntimeError("phase_c_budget_attempt_missing")
            matches[0]["result"] = result
            matches[0]["finished_at"] = time.time()
        pending = BUDGET.with_suffix(".pending")
        pending.write_text(json.dumps(value, indent=2), encoding="utf-8")
        os.replace(pending, BUDGET)
        return attempt_id, len(value["attempts"])
    finally:
        lock.unlink()


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


def _stop(process, *, tree=False):
    if process.poll() is not None:
        return
    if tree and os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _auth_read_result(events):
    for index, event in enumerate(events):
        item = (event.get("params") or {}).get("item") or {}
        if (event.get("method") != "item/completed" or
                item.get("type") != "commandExecution" or
                "auth.json" not in str(item.get("command", ""))):
            continue
        if item.get("exitCode") != 0:
            return "unverified", index
        output = str(item.get("aggregatedOutput", item.get("stdout", ""))).strip()
        if output == "AUTH_READ_EXIT=0":
            return "readable", index
        if output.startswith("AUTH_READ_EXIT=") and output[15:].isdigit() and \
                int(output[15:]) > 0:
            return "denied", index
        return "unverified", index
    return "missing", None


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
            "prompt_a": _digest(PROMPT_A),
            "skill": _digest(SKILL / "SKILL.md"),
            "source": _digest(SOURCE / "mediation-loop.mjs"),
            "client": _digest(ROOT / "laomedo" / "file_mediation_client.mjs"),
            "bridge": _digest(ROOT / "laomedo" / "file_mediation_bridge.py"),
            "implementation": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "model": MODEL, "effort": EFFORT, "turn_cap": TURN_CAP}
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
    run_a = None
    port = None
    api_token = None
    request_id = None
    attempt_id = None
    result_category = "not_submitted"
    teardown = {}
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
            "--max-model-turns", "1",
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
        prompt_a = PROMPT_A.read_text(encoding="utf-8")
        request_id = str(uuid4())
        body = {"request_id": request_id, "task": prompt_a,
                "model": MODEL, "effort": EFFORT,
                "skill_ref": {"skill_id": "phase-c-boundary",
                              "revision_id": skill["revision_id"],
                              "tree_hash": skill["revision_id"]},
                "github_authorization_ref": reference_a}
        attempt_id, attempt_number = _budget_update(state=state)
        pins["turns_before"] = attempt_number - 1
        pins["attempt_id"] = attempt_id
        (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
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
        raw = _events(event_path)
        auth_result, auth_event_index = _auth_read_result(raw)
        a_effects = [item for item in _journal(journal_path) if
                     item.get("run_id") == run_a]
        fake_receipts = _journal(service_state / "mediator" / "fake-provider.jsonl")
        active_result = {"run_id": run_a, "ack_status": active.get("status"),
                         "cancel_ack": cancel.get("status"),
                         "status": final_a.get("status"),
                         "cancel_confirmed": final_a.get("cancel_confirmed"),
                         "native_statuses": [e.get("params", {}).get("turn", {}).get("status")
                                             for e in raw
                                             if e.get("method") == "turn/completed"],
                         "auth_read": auth_result,
                         "auth_event_index": auth_event_index,
                         "fake_effects": a_effects,
                         "fake_receipt_count": len(fake_receipts),
                         "raw_event_sha256": _digest(event_path)}
        if time.monotonic() < long_started_at + 31:
            time.sleep(long_started_at + 31 - time.monotonic())
        active_result["sentinel_present_after_delay"] = (
            runs / run_a / "workspace" / "cancel-marker.txt").exists()
        owner = final_a.get("container_ownership") or {}
        inspected = (inspect_exact(owner["name"], run_a, owner["launch_token"])[0]
                     if owner.get("name") and owner.get("launch_token") else "unknown")
        active_result["container_absent"] = inspected == "absent"
        active_result["host_survived"] = host.poll() is None
        (state / "active-sanitized.json").write_text(
            json.dumps(active_result, indent=2), encoding="utf-8")
        if auth_result == "readable":
            raise RuntimeError("login_readable_stop")
        if (final_a.get("status") != "cancelled" or
                not final_a.get("cancel_confirmed") or
                auth_result != "denied" or
                "interrupted" not in active_result["native_statuses"] or
                len(a_effects) != 1 or
                a_effects[0].get("state") != "confirmed" or
                a_effects[0].get("effect_id") != "phase-c-cancel-0" or
                a_effects[0].get("provider_called") is not True or
                a_effects[0].get("replayed") is not False or
                len(fake_receipts) != 1 or
                fake_receipts[0].get("number") != 7 or
                active_result["sentinel_present_after_delay"] or
                not active_result["container_absent"] or
                not active_result["host_survived"]):
            raise RuntimeError("active_case_not_passed_no_kill_turn")
        result_category = "active_passed"

        # Phase B is deliberately not auto-dispatched here. The host must
        # inspect A's private trace and grant journal before spending turn 2.
    except Exception as error:
        result_category = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        raise
    finally:
        if run_a is None and request_id and runner is not None and \
                runner.poll() is None and port is not None and api_token:
            try:
                lookup = _request(port, api_token, "GET", "/v1/requests/" + request_id)
                run_a = lookup.get("run_id")
            except (OSError, ValueError):
                pass
        if run_a is None and request_id:
            for record_path in runs.glob("*/record.json"):
                try:
                    candidate = json.loads(record_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if candidate.get("client_request_id") == request_id:
                    run_a = candidate.get("run_id")
                    break
        if run_a and runner is not None and runner.poll() is None and \
                port is not None and api_token:
            try:
                status = _request(port, api_token, "GET", "/v1/runs/" + run_a)
                if status.get("status") in {"prepared", "running"}:
                    _request(port, api_token, "POST", f"/v1/runs/{run_a}/cancel", {})
                    status = _wait_run(port, api_token, run_a,
                        lambda x: x.get("status") not in {"prepared", "running"}, 30)
                teardown["terminal_status"] = status.get("status")
            except (OSError, ValueError, RuntimeError):
                teardown["terminal_status"] = "unknown"
        if runner is not None:
            _stop(runner, tree=True)
        lease_roots = list((service_state / "lease" / "leases").glob("*/lease.json"))
        for lease_path in lease_roots:
            try:
                lease = json.loads(lease_path.read_text(encoding="utf-8"))
                name, token, lease_run = (lease.get("name"), lease.get("token"),
                                          lease.get("run_id"))
                if not all(isinstance(value, str) and value for value in
                           (name, token, lease_run)):
                    continue
                lease_result = lease_path.parent / "result.json"
                try:
                    _wait(lease_result, 65)
                    teardown["lease_result_present"] = True
                except RuntimeError:
                    teardown["lease_result_present"] = False
                state_after, _ = inspect_exact(name, lease_run, token)
                teardown["container_state_after_lease"] = state_after
                if state_after != "absent":
                    verified, detail = cleanup_exact(name, lease_run, token)
                    teardown["emergency_cleanup"] = detail
                    teardown["container_absent"] = verified
                else:
                    teardown["container_absent"] = True
            except (OSError, ValueError):
                teardown["container_absent"] = False
        teardown["host_survived_until_cleanup"] = host.poll() is None
        _stop(host)
        if attempt_id is not None:
            try:
                _, count = _budget_update(attempt_id=attempt_id,
                                          result=result_category)
                teardown["budget_count_after"] = count
            except RuntimeError:
                teardown["budget_count_after"] = "unknown"
        ledger_path = runner_state / "turn-ledger.json"
        teardown["runner_submitted_turns"] = (
            json.loads(ledger_path.read_text(encoding="utf-8")).get("attempted_turns")
            if ledger_path.exists() else 0)
        teardown["run_id"] = run_a
        teardown["result_category"] = result_category
        (state / "teardown-sanitized.json").write_text(
            json.dumps(teardown, indent=2), encoding="utf-8")
        host_log.close()
        runner_log.close()
    if (teardown.get("budget_count_after") != attempt_number or
            teardown.get("runner_submitted_turns") != 1 or
            not teardown.get("container_absent") or
            not teardown.get("host_survived_until_cleanup")):
        raise RuntimeError("phase_c_teardown_unverified")
    print(json.dumps({"active": "passed", "run_id": run_a,
                      "turns_used": 1, "kill_case": "not_started"}))


if __name__ == "__main__":
    main()
