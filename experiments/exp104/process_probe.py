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
            output.write(json.dumps({"at": time.time(), "repository": repository,
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
            raise RuntimeError("exact_kill_failed")
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
    lease = context.Process(target=_lease_process,
                            args=(str(state), str(ledger), str(approvals)))
    mediator.start()
    lease.start()
    try:
        _wait(port_file)
        _wait(state / "service.alive")
        first, bearer_a = _register(authority, state, "a")
        second, bearer_b = _register(authority, state, "b")
        port = int(port_file.read_text(encoding="utf-8"))
        with sqlite3.connect(ledger) as db:
            expiries = [row[0] for row in db.execute("SELECT expires_at FROM grants")]
        if len(expiries) != 2:
            raise RuntimeError("grant_count_invalid")
        last_renewal = max(expiries) - 60
        loss_at = time.time()
        _kill_exact(lease)
        observations = []
        for index, delay in enumerate((0, 15, 30, 45, 60, 61)):
            while time.time() < loss_at + delay:
                time.sleep(min(.2, loss_at + delay - time.time()))
            if not mediator.is_alive():
                raise RuntimeError("mediator_did_not_survive")
            observations.append({"seconds_after_kill": round(time.time() - loss_at, 3),
                                 "a_status": _write(port, bearer_a, "a", index),
                                 "b_status": _write(port, bearer_b, "b", index)})
            if observations[-1]["a_status"] == observations[-1]["b_status"] == 403:
                break
        calls = [json.loads(line) for line in calls_file.read_text(encoding="utf-8").splitlines()]
        result = {"kind": "synthetic_separate_process_expiry",
                  "lease_pid": lease.pid, "mediator_pid": mediator.pid,
                  "lease_exitcode": lease.exitcode, "mediator_alive_after_kill": mediator.is_alive(),
                  "last_renewal_to_kill_seconds": round(loss_at - last_renewal, 3),
                  "observations": observations, "provider_call_count": len(calls),
                  "model_turns": 0, "github_tokens": 0}
        if (observations[-1]["a_status"] != 403 or observations[-1]["b_status"] != 403 or
                not result["mediator_alive_after_kill"] or
                any(row["a_status"] not in (200, 403) or row["b_status"] not in (200, 403)
                    for row in observations)):
            raise RuntimeError("expiry_gate_failed")
        return result
    finally:
        for process in (lease, mediator):
            if process.is_alive():
                process.terminate()
            process.join(10)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.state), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
