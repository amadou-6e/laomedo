"""Credential-free product-path gate for the independent Phase C bridge."""

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

from laomedo.file_mediation_bridge import FileMediationBridge
from laomedo.github_mediation import MediationStore
from laomedo.local_runner import LocalRunner
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.skill_store import SkillStore


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "experiments" / "exp22" / "phase-c-source"
SKILL = ROOT / "experiments" / "exp22" / "phase-c-skill"


def wait_file(path: Path, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(.05)
    raise RuntimeError("service_start_timeout")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="laomedo-phase-c-dry-") as temporary:
        state = args.state.resolve() if args.state else Path(temporary)
        if state.exists() and any(state.iterdir()):
            parser.error("dry_run_state_must_be_empty")
        state.mkdir(parents=True, exist_ok=True)
        runner_state = state / "runner"
        runs = runner_state / "runs"
        runs.mkdir(parents=True)
        service_state = state / "service"
        service_state.mkdir()
        authority = RunGrantAuthority(service_state / "authority.sqlite")
        store = SkillStore(state / "skills")
        skill_ref = store.import_skill("phase-c-boundary", SKILL)
        host_log = (state / "host.log").open("w", encoding="utf-8")
        host = subprocess.Popen([
            sys.executable, "-m", "experiments.exp22.phase_c_fake_host",
            "--state", str(service_state), "--runner-runs-root", str(runs)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=host_log,
            stderr=subprocess.STDOUT,
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0))
        try:
            wait_file(service_state / "lease" / "service.json", 8)
            wait_file(service_state / "mediator" / "file-bridge.json", 8)
            runner = LocalRunner(runner_state, state / "skills", SOURCE,
                                 max_model_turns=0,
                                 lease_service=service_state / "lease",
                                 github_authority=authority,
                                 mediator_state=service_state / "mediator",
                                 file_mediation=True)
            reference = authority.approve(
                invocation_id="dry-" + uuid4().hex,
                repository="example/disposable", branch="phase-c-a",
                operations={"pr_update"}, target_prs={7: "main"},
                reviewed_by="phase-c-synthetic")
            request = {"task": "No model turn: prepare only", "model": "gpt-6-luna",
                       "effort": "low", "skill_ref": {
                           "skill_id": "phase-c-boundary",
                           "revision_id": skill_ref["revision_id"],
                           "tree_hash": skill_ref["revision_id"]},
                       "github_authorization_ref": reference}
            record = runner._prepare(request)
            run_id = record["run_id"]
            lease_token = uuid4().hex
            name = "laomedo-codex-" + uuid4().hex
            record["container_ownership"] = {
                "name": name, "launch_token": lease_token,
                "supervised": True, "cleanup_verified": False}
            (runs / run_id / "record.json").write_text(
                json.dumps(record), encoding="utf-8")
            # The accepted lease is created by the real lease service. The
            # no-model check below uses its host-held grant, not a staged file.
            from laomedo.lease_service import LeaseClient
            import threading
            lease = LeaseClient(service_state / "lease", run_id=run_id,
                                name=name, token=lease_token,
                                cancelled=threading.Event(),
                                mediation_request=record["github_scope"])
            try:
                record["container_ownership"]["grant_id"] = lease.grant_id
                (runs / run_id / "record.json").write_text(
                    json.dumps(record), encoding="utf-8")
                runner._file_bridge_ready()
                body = {"repository": "example/disposable",
                        "operation": "pr_update", "effect_id": "dry-run-a",
                        "payload": {"number": 7, "head": "phase-c-a",
                                    "base": "main", "marker": "dry-run"}}
                (runs / run_id / "workspace" /
                 ".laomedo-req-dry-run-a.json").write_text(
                    json.dumps(body), encoding="utf-8")
                wait_file(runs / run_id / "bridge-responses" / "dry-run-a.json", 8)
                response = json.loads((runs / run_id / "bridge-responses" /
                                       "dry-run-a.json").read_text(encoding="utf-8"))
                journal = (service_state / "mediator" /
                           "file-bridge-journal.jsonl").read_text(encoding="utf-8")
                checked = {"host_pid": host.pid, "host_alive": host.poll() is None,
                           "bridge_ready": True,
                           "state": response.get("state"),
                           "journaled": '"effect_id": "dry-run-a"' in journal,
                           "turn_ledger_present": (runner_state / "turn-ledger.json").exists(),
                           "bearer_in_workspace": any("grant.secret" in p.name for p in
                                                      (runs / run_id / "workspace").iterdir())}
                print(json.dumps(checked, sort_keys=True))
                if (checked["state"] != "confirmed" or not checked["journaled"] or
                        checked["turn_ledger_present"] or checked["bearer_in_workspace"]):
                    raise RuntimeError("phase_c_product_dry_run_failed")
            finally:
                lease.finish()
        finally:
            host.terminate()
            try:
                host.wait(timeout=5)
            except subprocess.TimeoutExpired:
                host.kill()
                host.wait(timeout=5)
            host_log.close()


if __name__ == "__main__":
    main()
