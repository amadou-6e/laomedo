"""Bounded orphan/grant probe with a separate canary and host supervisor."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib import error, request


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
IMAGE = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
NETWORK = "laomedo-exp07-20261002"
BACKEND = "laomedo-exp07-backend-20261002"
WORKER = "laomedo-exp07-worker-20261002"
CANARY = "laomedo-exp07-canary-20261002"
STATE = "laomedo-exp07-state-20261002"
CANARY_STATE = "laomedo-exp07-canary-state-20261002"
URL = "http://127.0.0.1:17867"


def docker(*args, check=True, timeout=50):
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            timeout=timeout, check=False)
    if check and result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr[-400:]}")
    return result


def status():
    with request.urlopen(URL + "/status", timeout=3) as response:
        return json.load(response)


def health():
    with request.urlopen("http://127.0.0.1:17868/health", timeout=3) as response:
        return response.status == 200


def wait_for(predicate, seconds, label):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise TimeoutError(label)


def start_backend():
    docker("run", "-d", "--name", BACKEND, "--network", NETWORK,
           "-p", "127.0.0.1:17868:7860", "-e", "PYTHONPATH=/laomedo-src",
           "-e", "LANGFLOW_AUTO_LOGIN=true",
           "-e", "LANGFLOW_DO_NOT_TRACK=true",
           "-e", "LANGFLOW_DATABASE_URL=sqlite:////state/langflow.db",
           "-v", f"{STATE}:/state",
           "-v", f"{ROOT / 'experiments'}:/experiments:ro",
           "-v", f"{ROOT / 'laomedo'}:/laomedo-src/laomedo:ro",
           "--entrypoint", "python", IMAGE, "/experiments/exp06/start.py")
    wait_for(health, 100, "backend health")


def prepare_volume(name):
    docker("volume", "create", name)
    docker("run", "--rm", "--user", "root", "--network", "none",
           "-v", f"{name}:/state", "--entrypoint", "chown", IMAGE,
           "1000:0", "/state")


def cleanup():
    for name in (WORKER, BACKEND, CANARY):
        docker("rm", "-f", name, check=False)
    for name in (STATE, CANARY_STATE):
        docker("volume", "rm", name, check=False)
    docker("network", "rm", NETWORK, check=False)


def main(max_exposure_seconds):
    if not 1 <= max_exposure_seconds <= 300:
        raise ValueError("bounded exposure window required")
    for name in (BACKEND, WORKER, CANARY):
        if docker("inspect", name, check=False).returncode == 0:
            raise RuntimeError(f"existing container conflicts with EXP-07: {name}")
    for name in (STATE, CANARY_STATE):
        if docker("volume", "inspect", name, check=False).returncode == 0:
            raise RuntimeError(f"existing volume conflicts with EXP-07: {name}")
    if docker("network", "inspect", NETWORK, check=False).returncode == 0:
        raise RuntimeError("existing network conflicts with EXP-07")

    token = secrets.token_hex(32)
    report_path = HERE / "supervisor-report.json"
    report_path.unlink(missing_ok=True)
    supervisor = None
    try:
        docker("network", "create", NETWORK)
        prepare_volume(STATE)
        prepare_volume(CANARY_STATE)
        start_backend()
        docker("run", "-d", "--name", CANARY, "--network", NETWORK,
               "--network-alias", "canary", "-p", "127.0.0.1:17867:8099",
               "-e", "CANARY_GRANT=" + token,
               "-e", "CANARY_LEASE_NS=" + str(max_exposure_seconds * 1_000_000_000),
               "-v", f"{CANARY_STATE}:/canary-state",
               "-v", f"{HERE}:/fixture:ro", "--entrypoint", "python",
               IMAGE, "/fixture/canary.py")
        wait_for(status, 20, "canary startup")
        reservation = docker("run", "--rm", "--network", "none",
                             "-e", "PYTHONPATH=/laomedo-src", "-v", f"{STATE}:/state",
                             "-v", f"{HERE}:/fixture:ro",
                             "-v", f"{ROOT / 'laomedo'}:/laomedo-src/laomedo:ro",
                             "--entrypoint", "python", IMAGE, "/fixture/reserve.py")
        run_id = reservation.stdout.strip().splitlines()[-1]
        if len(run_id) != 36:
            raise RuntimeError("synthetic reservation ID missing")
        docker("run", "-d", "--name", WORKER, "--network", NETWORK,
               "-e", "CANARY_GRANT=" + token,
               "-e", "NO_PROXY=canary",
               "-v", f"{HERE}:/fixture:ro", "--entrypoint", "python",
               IMAGE, "/fixture/worker.py")
        wait_for(lambda: sum(e["accepted"] for e in status()["events"]
                             if e["action"] == "write") >= 3, 20, "canary writes")
        env = dict(os.environ, CANARY_GRANT=token,
                   EXP07_SUPERVISOR_REPORT=str(report_path))
        supervisor = subprocess.Popen([sys.executable, str(HERE / "supervisor.py")],
                                      env=env, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.PIPE)
        time.sleep(0.6)
        kill_requested_ns = time.time_ns()
        docker("kill", BACKEND)
        supervisor.communicate(timeout=max_exposure_seconds + 10)
        if supervisor.returncode != 0 or not report_path.exists():
            raise RuntimeError("independent supervisor failed")
        supervisor_report = json.loads(report_path.read_text(encoding="utf-8"))
        worker_state = docker("inspect", "--format", "{{.State.Status}}", WORKER).stdout.strip()
        worker_stop_observed_ns = time.time_ns()
        req = request.Request(URL + "/write", data=b"post-death-test", method="POST",
                              headers={"X-Test-Grant": token})
        try:
            with request.urlopen(req, timeout=3) as response:
                post_death_status = response.status
        except error.HTTPError as exc:
            post_death_status = exc.code
        canary = status()
        accepted_after_kill = [event for event in canary["events"]
                               if event["action"] == "write" and event["accepted"]
                               and event["at_ns"] >= kill_requested_ns]
        revoke_events = [event for event in canary["events"]
                         if event["action"] == "revoke" and event["accepted"]]
        if not revoke_events:
            raise RuntimeError("grant revocation was not observed")
        grant_end_ns = min(canary["expiry_ns"], revoke_events[0]["at_ns"])
        docker("rm", BACKEND)
        start_backend()
        after_restart = json.loads(docker("exec", BACKEND, "python",
                                          "/experiments/exp06/inspect_store.py",
                                          run_id).stdout)
        startup_sweep = "exp06_startup_swept=1" in docker("logs", BACKEND).stdout
        report = {"image": IMAGE, "selected_policy": "independent_supervisor_plus_startup_sweep",
                  "max_exposure_seconds": max_exposure_seconds,
                  "run_id": run_id, "kill_requested_ns": kill_requested_ns,
                  "supervisor": supervisor_report, "worker_state": worker_state,
                  "worker_stop_observed_ns": worker_stop_observed_ns,
                  "grant_expiry_ns": canary["expiry_ns"], "grant_end_ns": grant_end_ns,
                  "grant_exposure_ms_upper": max(0, (grant_end_ns-kill_requested_ns)/1e6),
                  "orphan_lifetime_ms_upper": max(0, (worker_stop_observed_ns-kill_requested_ns)/1e6),
                  "accepted_writes_after_kill": accepted_after_kill,
                  "post_death_grant_status": post_death_status,
                  "canary_events": canary["events"],
                  "startup_swept_one": startup_sweep,
                  "run_after_restart": after_restart}
        (HERE / "observation.json").write_text(json.dumps(report, indent=2) + "\n",
                                                encoding="utf-8")
        print(json.dumps({key: report[key] for key in (
            "grant_exposure_ms_upper", "orphan_lifetime_ms_upper",
            "post_death_grant_status", "startup_swept_one")}))
        bound_ms = max_exposure_seconds * 1000
        if (report["grant_exposure_ms_upper"] > bound_ms or
                report["orphan_lifetime_ms_upper"] > bound_ms or
                post_death_status != 403 or worker_state != "exited" or
                not startup_sweep or after_restart["status"] != "crashed"):
            raise AssertionError("EXP-07 orphan/grant bound failed")
    finally:
        if supervisor is not None and supervisor.poll() is None:
            supervisor.kill()
            supervisor.communicate(timeout=5)
        cleanup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-exposure-seconds", type=int, required=True)
    main(parser.parse_args().max_exposure_seconds)
