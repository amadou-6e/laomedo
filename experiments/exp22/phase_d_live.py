"""One-turn installed-Langflow graph cancellation probe for EXP-22 Phase D."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from uuid import uuid4

from experiments.exp22.phase_c_live import _auth_read_result, _budget_update, _events, _is_long_command
from laomedo.container_lease import cleanup_exact
from laomedo.local_runner import IMAGE as CODEX_IMAGE, LocalRunner, VOLUME, serve
from laomedo.skill_store import SkillStore


ROOT = Path(__file__).resolve().parents[2]
PILOT = ROOT / "examples" / "skill-agent-pilot"
PROTOCOL = ROOT / "experiments" / "exp22" / "PHASE-D-LANGFLOW-PROTOCOL.md"
TASK = ROOT / "experiments" / "exp22" / "PHASE-D-TASK.txt"
LANGFLOW_IMAGE = ("langflowai/langflow@sha256:"
                  "34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0")


def _hash(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _private_empty(path):
    path = path.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise RuntimeError("state_must_be_outside_git")
    if path.exists() and any(path.iterdir()):
        raise RuntimeError("state_must_be_empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _auth_mount_exists():
    probe = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none",
                            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                            "--user", "10001:10001", "--mount",
                            f"type=volume,source={VOLUME},target=/home/runner/.codex,readonly",
                            CODEX_IMAGE, "sh", "-c", "test -f /home/runner/.codex/auth.json"],
                           capture_output=True, timeout=20)
    return probe.returncode == 0


def _owned_container_absent(record):
    owner = record.get("container_ownership") or {}
    name = owner.get("name")
    if not name or not name.startswith("laomedo-codex-"):
        return False
    inspected = subprocess.run(["docker", "inspect", name], capture_output=True, timeout=12)
    listing = subprocess.run(["docker", "ps", "-a", "--filter", "name=^" + name + "$",
                              "--format", "{{.Names}}"], capture_output=True, text=True,
                             timeout=12)
    return (inspected.returncode != 0 and b"No such" in inspected.stderr and
            listing.returncode == 0 and not listing.stdout.strip())


def _audit_requests(server, path):
    """Record only route identity, never headers, bodies or API tokens."""
    original = server.RequestHandlerClass
    lock = threading.Lock()

    class AuditedHandler(original):
        def _record_route(self, method):
            route = self.path.split("?", 1)[0]
            kind = None
            if method == "POST" and route == "/v1/runs/async":
                kind = "start"
            elif method == "GET" and route.startswith("/v1/requests/"):
                kind = "lookup"
            elif (method == "POST" and route.startswith("/v1/runs/") and
                  route.endswith("/cancel")):
                kind = "cancel"
            if kind:
                with lock, path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"kind": kind, "path": route,
                                             "at_monotonic": time.monotonic()}) + "\n")

        def _authorized(self):
            authorized = super()._authorized()
            if authorized:
                self._record_route(self.command)
            return authorized

    server.RequestHandlerClass = AuditedHandler


def _route_summary(path, run_id, request_id):
    rows = _events(path)
    starts = [row for row in rows if row.get("kind") == "start"]
    lookups = [row for row in rows if row.get("kind") == "lookup"]
    cancels = [row for row in rows if row.get("kind") == "cancel"]
    expected_lookup = "/v1/requests/" + str(request_id)
    expected_cancel = "/v1/runs/" + str(run_id) + "/cancel"
    matched = (len(starts) == 1 and len(lookups) >= 1 and len(cancels) == 1 and
               all(row["path"] == expected_lookup for row in lookups) and
               cancels[0]["path"] == expected_cancel)
    return {"starts": len(starts), "lookups": len(lookups),
            "cancels": len(cancels), "exact_identity_match": matched}


def _cleanup_runner_runs(runner, runs_root, run_id, wait_seconds=20):
    recovered = list(runs_root.glob("*/record.json"))
    run_ids = {path.parent.name for path in recovered}
    if run_id:
        run_ids.add(run_id)
    results = []
    for owned_run_id in sorted(run_ids):
        one = {"run_id": owned_run_id, "terminal_status": None,
               "exact_cleanup_verified": None, "exact_cleanup_detail": None,
               "cancel_error": None, "status_error": None}
        try:
            try:
                observed = runner.status(owned_run_id)
                if observed["status"] in {"prepared", "running"}:
                    runner.cancel(owned_run_id)
            except Exception as exc:
                one["cancel_error"] = type(exc).__name__
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                try:
                    observed = runner.status(owned_run_id)
                except Exception as exc:
                    one["status_error"] = type(exc).__name__
                    break
                if observed.get("status") not in {"prepared", "running"}:
                    break
                time.sleep(.1)
            try:
                observed = runner.status(owned_run_id)
            except Exception as exc:
                one["status_error"] = type(exc).__name__
                observed = json.loads((runs_root / owned_run_id / "record.json").read_text(
                    encoding="utf-8"))
            one["terminal_status"] = observed.get("status")
            owner = observed.get("container_ownership") or {}
            if owner.get("name") and owner.get("launch_token"):
                if _owned_container_absent(observed):
                    one["exact_cleanup_verified"] = True
                    one["exact_cleanup_detail"] = "already_absent"
                else:
                    verified, detail = cleanup_exact(owner["name"], owned_run_id,
                                                     owner["launch_token"])
                    one["exact_cleanup_verified"] = bool(verified)
                    one["exact_cleanup_detail"] = detail
            else:
                one["exact_cleanup_verified"] = True
                one["exact_cleanup_detail"] = "not_launched"
        except Exception as exc:
            one["exact_cleanup_verified"] = False
            one["exact_cleanup_detail"] = type(exc).__name__
        results.append(one)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--allow-one-model-turn", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if args.allow_one_model_turn == args.preflight_only:
        parser.error("select_exactly_one_preflight_or_model_turn_mode")
    if (args.allow_one_model_turn and
            subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"],
                                    cwd=ROOT, text=True).strip()):
        parser.error("reviewed_source_must_be_committed_and_clean")
    state = _private_empty(args.state)
    graph_state = state / "graph"
    graph_state.mkdir()
    (graph_state / "task.txt").write_bytes(TASK.read_bytes())
    if not _auth_mount_exists():
        raise RuntimeError("private_login_copy_absent")
    reference = SkillStore(state / "skills").import_skill("laomedo-pilot", PILOT / "skill")
    runner = LocalRunner(state / "runner", state / "skills", PILOT / "source",
                         max_model_turns=1, supervise_containers=False)
    preflight = runner.preflight()
    if (preflight.get("status") != "ready" or preflight.get("image_id") is None or
            not any(item.get("id") == "gpt-6-luna" and "low" in item.get("efforts", [])
                    for item in preflight.get("models", []))):
        raise RuntimeError("runner_preflight_failed")
    if args.preflight_only:
        summary = {"provider_login_volume_present": True,
                   "runner_ready": True, "model_turn_submitted": False,
                   "codex_image_id": preflight["image_id"],
                   "skill_revision": reference["revision_id"]}
        (state / "preflight.json").write_text(json.dumps(summary, indent=2),
                                                encoding="utf-8")
        print(json.dumps(summary))
        return
    port = _port()
    server = serve(runner, port=port)
    audit_path = state / "runner-routes.jsonl"
    _audit_requests(server, audit_path)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    name = "laomedo-phase-d-graph-" + uuid4().hex[:16]
    pins = {"implementation": subprocess.check_output(["git", "rev-parse", "HEAD"],
                                                       cwd=ROOT, text=True).strip(),
            "protocol": _hash(PROTOCOL), "task": _hash(TASK),
            "flow": _hash(ROOT / "examples/native-codex-node/flow.json"),
            "component_source": _hash(ROOT / "components/laomedo/codex_agent.py"),
            "graph_child": _hash(ROOT / "experiments/exp22/phase_d_graph.py"),
            "skill": _hash(PILOT / "skill/SKILL.md"),
            "skill_revision": reference["revision_id"],
            "source": _hash(PILOT / "source/fixture.txt"),
            "codex_image_id": preflight["image_id"],
            "langflow_image": LANGFLOW_IMAGE, "model": "gpt-6-luna",
            "effort": "low", "shared_turn_cap": 4}
    (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
    output = (state / "graph.log").open("w", encoding="utf-8")
    child = None
    attempt_id = None
    category = "not_submitted"
    run_id = None
    failure_class = None
    try:
        command = ["docker", "run", "--rm", "--pull=never", "--name", name,
                   "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT},target=/workspace,readonly",
                   "--mount", f"type=bind,source={graph_state},target=/state",
                   "--mount", (f"type=bind,source={state / 'runner/api-token'},"
                               "target=/run/secrets/laomedo-runner-token,readonly"),
                   "-e", "PYTHONPATH=/workspace", "-e", "DO_NOT_TRACK=true",
                   "--entrypoint", "python",
                   LANGFLOW_IMAGE, "/workspace/experiments/exp22/phase_d_graph.py",
                   "--state", "/state", "--runner-port", str(port),
                   "--skill-id", "laomedo-pilot", "--revision-id",
                   reference["revision_id"]]
        attempt_id, used = _budget_update(state=state)
        category = "submitted_unknown"
        pins["turns_after_reservation"] = used
        (state / "pins.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
        if used != 4:
            raise RuntimeError("unexpected_shared_turn_count")
        child = subprocess.Popen(command, cwd=ROOT, stdout=output,
                                 stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 45
        long_started = False
        while time.monotonic() < deadline:
            records = list((state / "runner/runs").glob("*/record.json"))
            if len(records) > 1:
                raise RuntimeError("duplicate_runner_dispatch")
            if records:
                run_id = records[0].parent.name
                events = _events(records[0].parent / "raw-events.jsonl")
                auth_result, _ = _auth_read_result(events)
                if auth_result == "readable":
                    raise RuntimeError("agent_login_readable")
                if any(_is_long_command(event) for event in events):
                    long_started = True
                    break
            if child.poll() is not None:
                break
            time.sleep(.1)
        (graph_state / "stop.signal").write_text("stop", encoding="ascii")
        if child.poll() is None:
            child.wait(timeout=45)
        if not run_id:
            raise RuntimeError("runner_run_id_missing")
        terminal_deadline = time.monotonic() + 30
        while time.monotonic() < terminal_deadline:
            final = runner.status(run_id)
            if final["status"] not in {"prepared", "running"}:
                break
            time.sleep(.1)
        else:
            final = runner.status(run_id)
        events_path = state / "runner/runs" / run_id / "raw-events.jsonl"
        events = _events(events_path)
        auth_result, auth_event_index = _auth_read_result(events)
        native_statuses = [event.get("params", {}).get("turn", {}).get("status")
                           for event in events if event.get("method") == "turn/completed"]
        graph_result = json.loads((graph_state / "graph-result.json").read_text(encoding="utf-8"))
        time.sleep(31)
        marker = state / "runner/runs" / run_id / "workspace/cancel-marker.txt"
        result = {"run_id": run_id, "shared_turn_count": used,
                  "graph_outcome": graph_result.get("graph_outcome"),
                  "graph_stop_signal_seen": graph_result.get("stop_signal_seen"),
                  "long_command_started": long_started,
                  "auth_read": auth_result, "auth_event_index": auth_event_index,
                  "runner_status": final.get("status"),
                  "cancel_requested": final.get("cancel_requested"),
                  "cancel_confirmed": final.get("cancel_confirmed"),
                  "native_completion_statuses": native_statuses,
                  "raw_event_count": len(events), "raw_event_sha256": _hash(events_path),
                  "exact_container_absent": _owned_container_absent(final),
                  "late_sentinel_absent": not marker.exists()}
        routes = _route_summary(audit_path, run_id, final.get("client_request_id"))
        result["graph_runner_routes"] = routes
        run_count = len(list((state / "runner/runs").glob("*/record.json")))
        result["runner_run_count"] = run_count
        category = ("graph_native_cancel_passed" if
                    child.returncode == 0 and graph_result.get("stop_signal_seen") and
                    graph_result.get("graph_outcome") == "cancelled" and run_count == 1 and
                    routes["exact_identity_match"] and
                    long_started and auth_result == "denied" and
                    final.get("status") == "cancelled" and
                    final.get("cancel_confirmed") is True and
                    "interrupted" in native_statuses and
                    result["exact_container_absent"] and result["late_sentinel_absent"]
                    else "graph_native_cancel_inconclusive")
        result["category"] = category
        (state / "sanitized.json").write_text(json.dumps(result, indent=2),
                                               encoding="utf-8")
        print(json.dumps(result))
    except Exception as exc:
        failure_class = type(exc).__name__
        raise
    finally:
        teardown = {"run_id": run_id, "category": category,
                    "failure_class": failure_class, "terminal_status": None,
                    "exact_cleanup_verified": None, "exact_cleanup_detail": None,
                    "ledger_update_error": None, "graph_cleanup_error": None}
        try:
            if attempt_id:
                _budget_update(attempt_id=attempt_id, result=category)
        except Exception as exc:
            teardown["ledger_update_error"] = type(exc).__name__
        try:
            teardown["runs"] = _cleanup_runner_runs(
                runner, state / "runner/runs", run_id)
        except Exception as exc:
            teardown["runs"] = []
            teardown["run_cleanup_error"] = type(exc).__name__
        teardown["exact_cleanup_verified"] = all(
            row["exact_cleanup_verified"] for row in teardown["runs"]) if teardown["runs"] else False
        try:
            if child and child.poll() is None:
                removed = subprocess.run(["docker", "rm", "-f", name],
                                         capture_output=True, timeout=20)
                if removed.returncode != 0:
                    teardown["graph_cleanup_error"] = "docker_rm_failed"
                child.wait(timeout=20)
            inspected = subprocess.run(["docker", "inspect", name],
                                       capture_output=True, timeout=12)
            teardown["graph_container_absent"] = (
                inspected.returncode != 0 and b"No such" in inspected.stderr)
        except Exception as exc:
            teardown["graph_cleanup_error"] = type(exc).__name__
            teardown["graph_container_absent"] = False
        try:
            (state / "teardown.json").write_text(json.dumps(teardown, indent=2),
                                                 encoding="utf-8")
        finally:
            server.shutdown()
            server.server_close()
            output.close()


if __name__ == "__main__":
    main()
