"""Explicit standing local demo policy; each manual request gets its own budget.

The approved repository and exact report fixture remain bounded. This is not an
arbitrary repository coding service or an authorization boundary against the
same Windows user. Existing experiment state is never reset or reused.
"""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
from uuid import uuid4

from experiments.exp139 import runtime
from experiments.exp139.prepare import REPOSITORY, report_task, save
from laomedo.host.mediation.github_mediation import KnownRejected
from laomedo.agents.local_runner import LocalRunner, RunnerError

BRANCH = re.compile(r"laomedo-dev-[0-9a-f]{32}")


def policy(root):
    value = json.loads((root / "standing-policy.json").read_bytes())
    if (any(type(value.get(k)) is not int for k in ("turns_per_run", "pushes_per_run", "draft_prs_per_run")) or
            value.get("repository") != REPOSITORY or value.get("turns_per_run") != 4 or
            value.get("pushes_per_run") != 1 or value.get("draft_prs_per_run") != 1 or
            type(value.get("enabled")) is not bool):
        raise RunnerError("standing_policy_invalid")
    return value


def approved(root):
    value = policy(root)
    source = subprocess.check_output(["git", "-C", str(runtime.ROOT), "rev-parse", "HEAD"], text=True).strip()
    if value.get("reviewed_source") != source or not value["enabled"]:
        raise RunnerError("standing_policy_inactive")
    for relative, digest in value.get("input_hashes", {}).items():
        if sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise RunnerError("frozen_input_changed")
    if not value.get("input_hashes"):
        raise RunnerError("frozen_input_manifest_required")
    if subprocess.check_output(["git", "-C", str(runtime.ROOT), "status", "--porcelain"]).strip():
        raise RunnerError("exact_clean_source_required")


class PerRunWriteBudget:
    def __init__(self, path, transport, store, **_):
        self.path, self.transport, self.store = path, transport, store
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS per_run_attempts (run_id TEXT, operation TEXT, "
                       "PRIMARY KEY(run_id, operation))")

    def __call__(self, repository, operation, payload, **binding):
        if repository != REPOSITORY or operation not in {"git_push", "pr_create"}:
            raise KnownRejected("standing_operation_denied")
        branch = payload.get("branch") if operation == "git_push" else payload.get("head")
        if not isinstance(branch, str) or not BRANCH.fullmatch(branch):
            raise KnownRejected("standing_branch_denied")
        if operation == "git_push":
            stage = binding.get("verified_stage")
            if stage is None or stage.branch != branch or stage.repository != repository:
                raise KnownRejected("standing_verified_stage_required")
            run_id = stage.run_id
        else:
            with closing(self.store._connect()) as db:
                rows = db.execute("SELECT h.run_id FROM publication_handoffs h JOIN grants g "
                    "ON g.grant_id=h.grant_id WHERE g.repository=? AND g.branch=? "
                    "AND h.phase='publication_pending'", (repository, branch)).fetchall()
            if len(rows) != 1 or payload.get("draft") is not True:
                raise KnownRejected("standing_publisher_lane_required")
            run_id = rows[0]["run_id"]
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO per_run_attempts VALUES (?,?)", (run_id, operation))
            except sqlite3.IntegrityError:
                raise KnownRejected("standing_run_write_budget_consumed") from None
        return self.transport(repository, operation, payload, **binding)


class PersistentRunner(LocalRunner):
    def __init__(self, *args, approved_requests, authorization_factory, **kwargs):
        # The historical one-use binding remains untouched. Only this new
        # standing controller can create a fresh scope for an explicit start.
        for name in ("binding_state", "seed_consumed", "nonpublishing_lease_service"):
            kwargs.pop(name, None)
        # This historical harness owns its per-run four-turn policy; it must
        # never forward a test allowance into a normal runner.
        if kwargs.pop('max_model_turns', 4) != 4:
            raise RunnerError('standing_policy_mismatch')
        self.authorization_factory = authorization_factory
        self.local_run = threading.local()
        super().__init__(*args, **kwargs)
        self.policy_root = self.state.parent
        inputs = json.loads((self.policy_root / "flow-input/inputs.json").read_bytes())
        self.snapshot = inputs["snapshot"]
        config = json.loads((self.policy_root / "config.json").read_bytes())
        body_hash = sha256(self.snapshot["context"]["issue"]["body"].encode()).hexdigest()
        self.report = "\n".join(("# EXP-139 issue report", self.snapshot["context"]["issue"]["url"],
            "body_sha256: " + body_hash, self.snapshot["snapshot_id"], ""))
        if sha256(self.report.encode()).hexdigest() != config["report_sha256"]:
            raise RunnerError("frozen_report_mismatch")

    def _prepare(self, request, **kwargs):
        if not policy(self.policy_root)["enabled"]:
            raise RunnerError("standing_policy_inactive")
        if not isinstance(request, dict) or "github_authorization_ref" in request:
            raise RunnerError("standing_request_denied")
        if self.lock.locked() or any(
                json.loads(path.read_bytes()).get("status") in {"prepared", "running"}
                for path in (self.state / "runs").glob("*/record.json")):
            raise RunnerError("runner_busy")
        try:
            envelope = json.loads(request["task"])
        except (KeyError, ValueError, TypeError):
            raise RunnerError("standing_issue_context_required") from None
        if (envelope.get("frozen_issue") != self.snapshot or
                not isinstance(envelope.get("task"), str) or not envelope["task"].strip()):
            raise RunnerError("standing_issue_context_mismatch")
        # Keep the pinned skill/model/form defaults for this bounded demo.
        flow = json.loads((self.policy_root / "flow-input/success.json").read_bytes())
        from laomedo.agents.output_contract import requirements
        form = json.loads(next(n for n in flow["data"]["nodes"] if n["id"] == "contract")
                          ["data"]["node"]["template"]["requirements_json"]["value"])
        config = json.loads((self.policy_root / "config.json").read_bytes())
        expected = {"model": "gpt-6-luna", "effort": "low", "output_retries": 1,
                    "output_requirements": requirements(form),
                    "skill_ref": {k: config["skill"][k] for k in ("skill_id", "revision_id", "tree_hash")}}
        if {k: v for k, v in request.items() if k not in {"task", "request_id"}} != expected:
            raise RunnerError("standing_pinned_inputs_required")
        branch = "laomedo-dev-" + uuid4().hex
        selected = deepcopy(request)
        selected["task"] = json.dumps({"task": envelope["task"] + "\n\n" + report_task(self.report, branch),
                                      "frozen_issue": self.snapshot}, sort_keys=True, ensure_ascii=False)
        selected["github_authorization_ref"] = self.authorization_factory(branch)
        record = super()._prepare(selected, **kwargs)
        save(self._run_dir(record["run_id"]) / "prepared-task.json", {"task": selected["task"], "branch": branch})
        return record

    def _ledger(self):
        run_id = getattr(self.local_run, "run_id", None)
        if run_id is None:
            raise RunnerError("per_run_ledger_required")
        return self._run_dir(run_id) / "turn-ledger.json"

    def _turn_available(self):
        path = self._ledger()
        count = json.loads(path.read_bytes())["attempted_turns"] if path.exists() else 0
        if type(count) is not int or not 0 <= count < 4:
            raise RunnerError("model_turn_cap_reached")

    def _reserve_turn(self):
        self._turn_available()
        path = self._ledger()
        count = json.loads(path.read_bytes())["attempted_turns"] if path.exists() else 0
        save(path, {"attempted_turns": count + 1, "max_authorized_turns": 4})
        return count + 1

    def _execute(self, run_id, task, *, resume):
        if resume:
            raise RunnerError("standing_resume_unsupported")
        self.local_run.run_id = run_id
        try:
            prepared = json.loads((self._run_dir(run_id) / "prepared-task.json").read_bytes())
            return super()._execute(run_id, prepared["task"], resume=False)
        finally:
            self.local_run.run_id = None

    def resume(self, *args, **kwargs):
        raise RunnerError("standing_resume_unsupported")


def composition(root):
    return runtime.composition(root, budget_class=PerRunWriteBudget)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("services", "runner"))
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    if args.role == "services":
        runtime.services(args.state, startup_check=approved, composition_factory=composition)
    else:
        runtime.runner(args.state, startup_check=approved, composition_factory=composition,
                       engine_class=PersistentRunner, port=8780)
