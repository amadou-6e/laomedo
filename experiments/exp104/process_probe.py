"""One-shot, no-credential hard-kill probe for separate lease/mediator processes.

Run only with a fresh absolute --state path outside a checkout. The output is
sanitized JSON: it never contains bearer values or credential hashes. This is
synthetic evidence, not the scoped GitHub identity case in LIVE-PROTOCOL.md.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import threading
import time
from urllib import error, request

from laomedo.github_mediation import MediationStore
from laomedo.lease_service import LeaseService
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService


REPOSITORY = "example/disposable"


def _lease_process(state: str, ledger: str, authority: str) -> None:
    service = LeaseService(Path(state), mediator=MediationStore(Path(ledger)),
                           mediation_authority=RunGrantAuthority(Path(authority)).authorize_lease,
                           cleanup=lambda *_: (True, "synthetic_cleanup"))
    service.serve()


def _mediator_process(ledger: str, port_file: str, calls_file: str) -> None:
    def synthetic_transport(repository, operation, payload):
        with Path(calls_file).open("a", encoding="utf-8") as output:
            output.write(json.dumps({"at_wall": time.time(),
                                     "at_monotonic": time.monotonic(),
                                     "repository": repository,
                                     "operation": operation}) + "\n")
        return {"synthetic": True}

    service = MediationHTTPService(MediationStore(Path(ledger)), synthetic_transport)
    Path(port_file).write_text(str(service.port), encoding="utf-8")
    try:
        service.serve()
    finally:
        service.server.server_close()


def _wait(path: Path, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(.05)
    raise RuntimeError("process_ready_timeout")


def _register(authority: RunGrantAuthority, state: Path, run_id: str) -> tuple[Path, str]:
    branch = "probe-" + run_id
    ref = authority.approve(invocation_id="invocation-" + run_id,
                            repository=REPOSITORY, branch=branch,
                            operations={"pr_update"}, target_prs={7: "main"},
                            reviewed_by="synthetic-protocol")
    authority.bind_run(ref, run_id)
    token = "lease-" + run_id
    directory = state / "leases" / token
    directory.mkdir()
    (directory / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
    (directory / "lease.json").write_text(json.dumps({
        "token": token, "run_id": run_id, "name": "synthetic-" + run_id,
        "mediation": {"invocation_id": "invocation-" + run_id,
                      "repository": REPOSITORY, "branch": branch}}), encoding="utf-8")
    _wait(directory / "accepted.json")
    return directory, (directory / "grant.secret").read_text(encoding="utf-8")


def _write(port: int, bearer: str, run_id: str, index: int) -> int:
    body = json.dumps({"repository": REPOSITORY, "operation": "pr_update",
                       "payload": {"number": 7, "head": "probe-" + run_id,
                                   "base": "main", "marker": "probe"},
                       "effect_id": f"{run_id}-{index}"}).encode()
    call = request.Request(f"http://127.0.0.1:{port}/v1/mediate", data=body,
                           method="POST", headers={"Authorization": "Bearer " + bearer,
                                                   "Content-Type": "application/json"})
    try:
        with request.urlopen(call, timeout=5) as response:
            return response.status
    except error.HTTPError as failure:
        return failure.code


def _kill_exact(process: multiprocessing.Process) -> None:
    if process.pid is None or not process.is_alive():
        raise RuntimeError("lease_process_not_alive")
    if os.name == "nt":
        result = subprocess.run(["taskkill", "/PID", str(process.pid), "/F"],
                                capture_output=True, timeout=10)
        if result.returncode:
            # No bearer is passed to taskkill; its diagnostic is safe to keep.
            detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"exact_kill_failed:{result.returncode}:{detail}")
    else:
        os.kill(process.pid, signal.SIGKILL)
    process.join(10)
    if process.is_alive():
        raise RuntimeError("lease_process_survived_kill")


def run(state: Path) -> dict:
    state = state.resolve()
    if state.exists() or any((parent / ".git").exists() for parent in
                             (state.parent, *state.parent.parents)):
        raise RuntimeError("fresh_private_state_outside_checkout_required")
    state.mkdir(parents=True)
    ledger, approvals = state / "mediator.sqlite", state / "authority.sqlite"
    port_file, calls_file = state / "mediator-port", state / "provider-calls.jsonl"
    authority = RunGrantAuthority(approvals)
    MediationStore(ledger)
    context = multiprocessing.get_context("spawn")
    mediator = context.Process(target=_mediator_process,
                               args=(str(ledger), str(port_file), str(calls_file)))
    a_state, b_state = state / "service-a", state / "service-b"
    lease_a = context.Process(target=_lease_process,
                              args=(str(a_state), str(ledger), str(approvals)))
    lease_b = context.Process(target=_lease_process,
                              args=(str(b_state), str(ledger), str(approvals)))
    keep_b_alive = threading.Event()
    heartbeat_thread = None
    mediator.start()
    lease_a.start()
    lease_b.start()
    try:
        _wait(port_file)
        _wait(a_state / "service.alive")
        _wait(b_state / "service.alive")
        first, bearer_a = _register(authority, a_state, "a")
        second, bearer_b = _register(authority, b_state, "b")
        def heartbeat_b() -> None:
            while not keep_b_alive.is_set():
                (second / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
                keep_b_alive.wait(1)
        heartbeat_thread = threading.Thread(target=heartbeat_b, daemon=True)
        heartbeat_thread.start()
        port = int(port_file.read_text(encoding="utf-8"))
        with sqlite3.connect(ledger) as db:
            expiries = [row[0] for row in db.execute("SELECT expires_at FROM grants")]
        if len(expiries) != 2 or not lease_b.is_alive():
            raise RuntimeError("grant_count_invalid")
        last_renewal = max(expiries) - 60
        kill_started_monotonic = time.monotonic()
        _kill_exact(lease_a)
        kill_completed_monotonic = time.monotonic()
        kill_completed_wall = time.time()
        observations = []
        for index, delay in enumerate((0, 15, 30, 45, 60, 61)):
            while time.monotonic() < kill_completed_monotonic + delay:
                time.sleep(min(.2, kill_completed_monotonic + delay - time.monotonic()))
            if not mediator.is_alive() or not lease_b.is_alive():
                raise RuntimeError("surviving_service_not_alive")
            observed_at = time.monotonic()
            observations.append({"at_monotonic": observed_at,
                                 "seconds_after_kill": round(observed_at - kill_completed_monotonic, 3),
                                 "a_status": _write(port, bearer_a, "a", index),
                                 "b_status": _write(port, bearer_b, "b", index)})
            if observations[-1]["a_status"] == 403:
                break
        calls = [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines()]
        result = {"kind": "synthetic_separate_process_expiry",
                  "lease_a_pid": lease_a.pid, "lease_b_pid": lease_b.pid,
                  "mediator_pid": mediator.pid,
                  "lease_a_exitcode": lease_a.exitcode,
                  "lease_b_alive_after_a_kill": lease_b.is_alive(),
                  "mediator_alive_after_kill": mediator.is_alive(),
                  "kill_started_monotonic": kill_started_monotonic,
                  "kill_completed_monotonic": kill_completed_monotonic,
                  "last_renewal_to_kill_wall_seconds": round(
                      kill_completed_wall - last_renewal, 3),
                  "observations": observations, "provider_call_count": len(calls),
                  "provider_calls": calls,
                  "model_turns": 0, "github_tokens": 0}
        accepted = sum(row["a_status"] == 200 for row in observations) + sum(
            row["b_status"] == 200 for row in observations)
        if (observations[-1]["a_status"] != 403 or
                any(row["b_status"] != 200 for row in observations) or
                not result["mediator_alive_after_kill"] or
                not result["lease_b_alive_after_a_kill"] or
                len(calls) != accepted or
                any(row["a_status"] not in (200, 403) or row["b_status"] not in (200, 403)
                    for row in observations)):
            raise RuntimeError("expiry_gate_failed")
        return result
    finally:
        keep_b_alive.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(5)
        for process in (lease_a, lease_b, mediator):
            if process.is_alive():
                process.terminate()
            process.join(10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--record", type=Path,
                        help="write the machine observation once, with LF endings")
    args = parser.parse_args()
    if args.record is not None and (args.record.exists() or not args.record.parent.is_dir()):
        parser.error("record_target_must_be_new_in_existing_directory")
    result = run(args.state)
    content = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.record is not None:
        with args.record.open("x", encoding="utf-8", newline="\n") as observation:
            observation.write(content)
        print(json.dumps({"recorded": str(args.record),
                          "provider_call_count": result["provider_call_count"]}))
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
