"""One-shot EXP-93 amendment 2: independent lease service under a whole-tree kill."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib import error, request
from uuid import uuid4

from laomedo.container_lease import LABEL_RUN, LABEL_TOKEN, inspect_exact
from laomedo.lease_service import LeaseClient


OUTPUT = Path(__file__).with_name("service-observation.json")
ROOT = Path(__file__).resolve().parents[2]
IMAGE = "laomedo-codex-boundary:0.159.2"
LOOKALIKE_LABEL = "laomedo.experiment=exp93-service-lookalike"
WRITER = """
const grant = process.env.GRANT, port = process.env.PORT;
setInterval(() => {
  fetch(`http://host.docker.internal:${port}/write`, {method: 'POST',
    headers: {Authorization: `Bearer ${grant}`}, body: '{}'}).catch(() => {});
}, 200);
"""


def command_line(pid: int) -> str:
    response = subprocess.run(["powershell", "-NoProfile", "-Command",
        f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"],
        capture_output=True, text=True, timeout=10)
    return response.stdout.strip()


def docker_json(name: str) -> dict | None:
    result = subprocess.run(["docker", "inspect", name], capture_output=True,
                            text=True, timeout=10)
    return json.loads(result.stdout)[0] if result.returncode == 0 else None


def child(root: Path, service_state: Path) -> None:
    run_id, token = uuid4().hex, uuid4().hex
    name = "laomedo-codex-" + uuid4().hex
    lease = LeaseClient(service_state, run_id=run_id, name=name, token=token,
                        cancelled=threading.Event())
    info = json.loads((service_state / "service.json").read_text(encoding="utf-8"))
    subprocess.run(["docker", "run", "-d", "--name", name, "--pull=never",
        "--label", f"{LABEL_RUN}={run_id}", "--label", f"{LABEL_TOKEN}={token}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--user", "10001:10001", "--network", "bridge",
        "--env", "GRANT=" + lease.grant_secret(), "--env", f"PORT={info['port']}",
        "--entrypoint", "node", IMAGE, "-e", WRITER],
        check=True, capture_output=True, timeout=60)
    (root / "identities.json").write_text(json.dumps({
        "child_pid": os.getpid(), "service_pid": info["pid"], "run_id": run_id,
        "name": name, "token": token, "grant_id": lease.grant_id}), encoding="utf-8")
    while True:
        time.sleep(1)


def write_status(port: int, secret: str) -> int:
    req = request.Request(f"http://127.0.0.1:{port}/write", data=b"{}", method="POST",
                          headers={"Authorization": "Bearer " + secret})
    try:
        with request.urlopen(req, timeout=5) as response:
            return response.status
    except error.HTTPError as exc:
        return exc.code


def events(service_state: Path) -> list[dict]:
    path = service_state / "grant-events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "child":
        child(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve())
        return
    if len(sys.argv) != 1 or os.name != "nt":
        raise SystemExit("Windows-only one-shot probe")
    if OUTPUT.exists():
        raise SystemExit("observation_exists_no_retry")
    root = Path(tempfile.mkdtemp(prefix="laomedo-exp93-service-"))
    service_state = root / "service"
    lookalike = "laomedo-codex-lookalike-" + uuid4().hex
    service = subprocess.Popen([sys.executable, "-m", "laomedo.lease_service", "serve",
                                "--state", str(service_state)], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    runner = None
    identities: dict = {}
    killed = False
    try:
        until = time.monotonic() + 15
        while time.monotonic() < until and not (service_state / "service.alive").exists():
            time.sleep(.05)
        info = json.loads((service_state / "service.json").read_text(encoding="utf-8"))
        if info["pid"] != service.pid:
            raise RuntimeError("service_identity_mismatch")
        subprocess.run(["docker", "run", "-d", "--name", lookalike, "--pull=never",
                        "--label", LOOKALIKE_LABEL, "--network", "none",
                        "--entrypoint", "sleep", IMAGE, "600"],
                       check=True, capture_output=True, timeout=60)
        runner = subprocess.Popen([sys.executable, "-m", "experiments.exp93.service_probe",
                                   "child", str(root), str(service_state)], cwd=ROOT,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic() + 60
        while time.monotonic() < until and not (root / "identities.json").exists():
            if runner.poll() is not None:
                raise RuntimeError("runner_exited_before_ready")
            time.sleep(.1)
        identities = json.loads((root / "identities.json").read_text(encoding="utf-8"))
        if identities["child_pid"] != runner.pid or identities["service_pid"] != service.pid:
            raise RuntimeError("process_identity_mismatch")
        if ("experiments.exp93.service_probe" not in command_line(runner.pid) or
                "laomedo.lease_service" not in command_line(service.pid)):
            raise RuntimeError("process_command_mismatch")
        name, run_id, token = identities["name"], identities["run_id"], identities["token"]
        secret = (service_state / "leases" / token / "grant.secret").read_text(encoding="utf-8")
        until = time.monotonic() + 30
        accepted_before = 0
        while time.monotonic() < until:
            entry = docker_json(name)
            accepted_before = sum(1 for e in events(service_state)
                                  if e["grant_id"] == identities["grant_id"] and e["accepted"])
            if (entry and entry["State"]["Running"] and accepted_before and
                    inspect_exact(name, run_id, token)[0] == "owned"):
                break
            time.sleep(.2)
        else:
            raise RuntimeError("owned_writer_not_ready")

        killed_at = time.time()
        subprocess.run(["taskkill", "/PID", str(runner.pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=10, check=True)
        killed = True
        result_path = service_state / "leases" / token / "result.json"
        result, absent_at = None, None
        until = time.monotonic() + 60
        while time.monotonic() < until and (result is None or absent_at is None):
            if result is None and result_path.exists():
                result = json.loads(result_path.read_text(encoding="utf-8"))
            if absent_at is None and inspect_exact(name, run_id, token)[0] == "absent":
                absent_at = time.time()
            time.sleep(.1)

        alive_at = float((service_state / "service.alive").read_text(encoding="utf-8"))
        service_survived = (service.poll() is None and time.time() - alive_at < 3 and
                            "laomedo.lease_service" in command_line(service.pid))
        post_status = write_status(info["port"], secret) if result else None
        revoked_at = result["revoked_at"] if result else None
        accepted_after = (sum(1 for e in events(service_state)
                              if e["grant_id"] == identities["grant_id"] and e["accepted"]
                              and e["at"] > revoked_at) if revoked_at else None)
        look = docker_json(lookalike)
        lookalike_running = bool(look and look["State"]["Running"] and
                                 look["Config"]["Labels"].get("laomedo.experiment") ==
                                 LOOKALIKE_LABEL.split("=", 1)[1])
        to_revoke = round(revoked_at - killed_at, 3) if revoked_at else None
        to_absent = round(absent_at - killed_at, 3) if absent_at else None
        passed = bool(service_survived and result and
                      result.get("reason") == "heartbeat_lost" and
                      identities["grant_id"] in result.get("revoked_grants", []) and
                      result.get("cleanup_verified") is True and
                      to_revoke is not None and to_revoke < 60 and
                      to_absent is not None and to_absent < 60 and
                      accepted_after == 0 and post_status == 403 and lookalike_running)
        version = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        observed = {"schema_version": 1, "model_turns": 0, "github_tokens": 0,
            "kill_scope": "taskkill_exact_runner_tree", "docker_engine": version,
            "image": IMAGE, "service_survived": service_survived,
            "result_reason": result.get("reason") if result else None,
            "grant_revoked": bool(result and identities["grant_id"] in
                                  result.get("revoked_grants", [])),
            "cleanup_verified": result.get("cleanup_verified") if result else None,
            "cleanup_state": result.get("state") if result else None,
            "seconds_kill_to_revocation": to_revoke,
            "seconds_kill_to_container_absent": to_absent,
            "accepted_writes_before_kill": accepted_before,
            "accepted_writes_after_revocation": accepted_after,
            "post_revocation_write_status": post_status,
            "lookalike_running": lookalike_running,
            "bound_seconds": 60,
            "classification": "pass" if passed else "fail"}
        OUTPUT.write_text(json.dumps(observed, indent=2) + "\n", encoding="utf-8",
                          newline="\n")
        print(json.dumps(observed))
    finally:
        if runner is not None and not killed and runner.poll() is None:
            subprocess.run(["taskkill", "/PID", str(runner.pid), "/T", "/F"],
                           capture_output=True, timeout=10)
        if identities and inspect_exact(identities["name"], identities["run_id"],
                                        identities["token"])[0] == "owned":
            subprocess.run(["docker", "rm", "-f", identities["name"]],
                           capture_output=True, timeout=15)
        look = docker_json(lookalike)
        if look and look["Config"]["Labels"].get("laomedo.experiment") == \
                LOOKALIKE_LABEL.split("=", 1)[1]:
            subprocess.run(["docker", "rm", "-f", look["Id"]], capture_output=True, timeout=15)
        if service.poll() is None and "laomedo.lease_service" in command_line(service.pid):
            subprocess.run(["taskkill", "/PID", str(service.pid), "/F"],
                           capture_output=True, timeout=10)


if __name__ == "__main__":
    main()
