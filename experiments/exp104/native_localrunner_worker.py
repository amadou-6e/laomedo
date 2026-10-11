"""S13 production LocalRunner fixture held at native initialize; zero turns."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from laomedo.container_lease import inspect_exact
from laomedo.github_git_transport import _base_git_environment
from laomedo.local_runner import AppServer, LocalRunner, RunnerError
from laomedo.mediation_authority import RunGrantAuthority
from laomedo import workspace_skills

IDENTITY = "exp104-localrunner-s13-20261010-a"


def identities(side, root=None):
    if side not in ("a", "b"):
        raise ValueError("invalid_side")
    value = {"branch": IDENTITY + "-" + side,
             "invocation_id": IDENTITY + "-invocation-" + side}
    if root is not None:
        records = []
        for path in (root / "runner/runs").glob("*/record.json"):
            record = json.loads(path.read_bytes())
            if (record.get("github_scope") or {}).get("branch") == value["branch"]:
                records.append(record)
        if len(records) > 1:
            raise ValueError("run_identity_conflict")
        if records:
            record = records[0]
            owner = record.get("container_ownership") or {}
            value.update(run_id=record["run_id"], name=owner.get("name"),
                         token=owner.get("launch_token"))
    return value


def zero_turns(state):
    ledger = state / "turn-ledger.json"
    if ledger.exists() and json.loads(ledger.read_bytes()).get("attempted_turns") != 0:
        raise ValueError("unexpected_model_turn")


def run(root, side):
    from experiments.exp104.native_managed_probe import save
    authority = RunGrantAuthority(root / "host/authority.sqlite")

    class HeldInitialize(AppServer):
        """Only instrument the native response boundary, never the launch args."""
        def __init__(self, command, evidence):
            owner = json.loads((evidence / "record.json").read_bytes())["container_ownership"]
            capability = (root / "host/lease/leases" / owner["launch_token"] / "grant.secret").read_text().strip()
            super().__init__(command, evidence, secret_redactions=(capability,))

        def request(self, method, params, timeout=30):
            if method != "initialize":
                raise RunnerError("fixture_forbids_model_or_thread_request")
            response = super().request(method, params, timeout)
            if "result" not in response:
                raise RunnerError("fixture_initialize_rejected")
            selected = identities(side, root)
            state, container_id = inspect_exact(selected["name"], selected["run_id"], selected["token"])
            if state != "owned":
                raise RunnerError("fixture_container_not_owned")
            record = runner.status(selected["run_id"])
            workspace = runner.state / "runs" / selected["run_id"] / "workspace"
            workspace_skills.verify(workspace, record["skills"], record["skill_git_exclusion"])
            zero_turns(runner.state)
            save(root / (side + "-ready.json"), {
                **selected, "pid": os.getpid(), "container_id": container_id,
                "grant_id": record["container_ownership"]["grant_id"],
                "native_initialize": True, "requests": ["initialize"],
                "raw_events_sha256": sha256((workspace.parent / "raw-events.jsonl").read_bytes()).hexdigest(),
                "record_sha256": sha256((workspace.parent / "record.json").read_bytes()).hexdigest(),
                "skill_exclude_sha256": record["skill_git_exclusion"]["exclude_sha256"],
                "model_turns": 0, "production_launch": True})
            deadline = float((root / "deadline").read_text())
            while not (root / (side + "-stop")).exists() and time.monotonic() < deadline:
                time.sleep(.1)
            # Do not return a success and let production proceed to a thread.
            raise RunnerError("fixture_hold_finished_before_turn")

    # This constructor uses real image/volume checks and startup recovery.
    # Both instances finish construction BEFORE the controller opens the gate.
    runner = LocalRunner(root / "runner", root / "skill-store", root / ("source-" + side),
        transport=HeldInitialize, max_model_turns=0, git_workspace=True,
        supervise_containers=True, lease_service=root / "host/lease",
        github_authority=authority, mediator_state=root / "host/mediator")
    save(root / (side + "-initialized.json"), {"pid": os.getpid(), "constructed": True})
    deadline = float((root / "deadline").read_text())
    while not (root / "start-gate").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("fixture_gate_deadline")
        time.sleep(.1)
    authorization = json.loads((root / (side + "-authorization.json")).read_bytes())
    reference = json.loads((root / "skill-reference.json").read_bytes())
    prepared = runner._prepare({"task": "No model turn; native initialize hold only",
        "model": "gpt-6-luna", "effort": "low", "skill_ref": reference,
        "github_authorization_ref": authorization})
    result = runner._execute(prepared["run_id"], "No model turn", resume=False)
    zero_turns(runner.state)
    save(root / (side + "-finished.json"), {"run_id": result["run_id"],
         "status": result["status"], "error_category": result["error_category"], "model_turns": 0})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--side", choices=("a", "b"), required=True)
    args = parser.parse_args()
    try:
        run(args.root.resolve(), args.side)
    except Exception as failure:
        print(json.dumps({"status": "fixture_failed", "error_class": type(failure).__name__}))
        raise SystemExit(1)
