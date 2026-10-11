"""Explicit, disposable host composition. Never starts merely by importing.

Run services and runner as separate host processes only after configuration and
exact-source review approval. No credential or grant enters the Langflow graph.
"""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import threading

from experiments.exp139.bindings import BoundRunner, request_digest
from experiments.exp139.prepare import connection, IDENTITY, REPOSITORY, BRANCH
from laomedo.bundle_stage import verify_frozen_bundle
from laomedo.github_git_transport import GitHubGitTransport, GitHubMediatedTransport
from laomedo.github_mediation import MediationStore, KnownRejected
from laomedo.github_rest_transport import GitHubRestTransport
from laomedo.host_services import serve_services
from laomedo.lease_service import LeaseService
from laomedo.local_runner import GIT_IMAGE_ID, serve
from laomedo.mediation_authority import RunGrantAuthority
from laomedo.mediation_service import MediationHTTPService, JournaledTransport
from laomedo.output_contract import requirements
from laomedo.publication_controller import PublicationController
from laomedo.siwc_auth import _outside_git
from laomedo.verified_git_stage import make_grant_bundle_freezer, make_grant_stage_resolver, stage_verified_git

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = "experiments/exp139/issue-report.md"


def configuration(root):
    root = _outside_git(root)
    config = json.loads((root / "config.json").read_bytes())
    if (config.get("identity") != IDENTITY or config.get("repository") != REPOSITORY or
            config.get("branch") != BRANCH or config.get("turn_cap") != 4 or
            config.get("runner_port") != 8779 or config.get("handoff_seconds") != 600):
        raise ValueError("frozen_configuration_required")
    return root, config


def approved(root):
    """Require concrete activation and exact-source review records, not a CLI flag."""
    source = __import__("subprocess").check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    manifest = root / "manifest.json"
    approval = json.loads((root / "activation.json").read_bytes())
    expected = {"identity": IDENTITY, "source_sha": source,
                "manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
                "configuration_approved": True, "review_verdict": "approve"}
    if approval != expected:
        raise ValueError("exact_activation_review_required")
    frozen = json.loads(manifest.read_bytes())
    for relative, digest in frozen["source_hashes"].items():
        if sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen_source_changed")
    for relative, digest in frozen["input_hashes"].items():
        if sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen_input_changed")


class WriteBudget:
    """Durable attempt budget; reserve before provider dispatch, never reset."""
    def __init__(self, path, transport, store):
        self.path, self.transport, self.store = path, transport, store
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (operation TEXT PRIMARY KEY)")

    def __call__(self, repository, operation, payload, **binding):
        if repository != REPOSITORY or operation not in {"git_push", "pr_create"}:
            raise KnownRejected("experiment_operation_denied")
        if operation == "git_push" and payload.get("branch") != BRANCH:
            raise KnownRejected("experiment_branch_denied")
        if operation == "pr_create":
            with closing(self.store._connect()) as db:
                rows = db.execute("SELECT h.phase FROM publication_handoffs h JOIN grants g "
                    "ON g.grant_id=h.grant_id WHERE g.repository=? AND g.branch=?",
                    (REPOSITORY, BRANCH)).fetchall()
            if (len(rows) != 1 or rows[0]["phase"] != "publication_pending" or
                    payload.get("head") != BRANCH or payload.get("draft") is not True):
                raise KnownRejected("experiment_publisher_lane_required")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO attempts VALUES (?)", (operation,))
            except sqlite3.IntegrityError:
                raise KnownRejected("experiment_write_budget_consumed") from None
        return self.transport(repository, operation, payload, **binding)


def composition(root):
    root, config = configuration(root)
    host = root / "host"
    host.mkdir(exist_ok=True)
    (host / "mediator").mkdir(exist_ok=True)
    provider = connection(root, Path(config["token_file"]))
    rest = GitHubRestTransport(REPOSITORY, provider.token)
    resolver = make_grant_stage_resolver(root / "runner", root / "private-stage", root / "runner")
    def checked_stage(grant, repository, payload):
        snapshot = resolver(grant, repository, payload)
        with stage_verified_git(snapshot) as staged:
            diff = staged.git("diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z",
                              "--no-renames", snapshot.baseline, snapshot.commit)
            content = staged.git("show", snapshot.commit + ":" + REPORT_PATH)
            if (diff.returncode or diff.stdout != REPORT_PATH.encode() + b"\0" or
                    content.returncode or sha256(content.stdout).hexdigest() != config["report_sha256"]):
                raise ValueError("bounded_report_artifact_required")
        return snapshot
    store = MediationStore(host / "mediator/mediator.sqlite",
        verified_stage_resolver=checked_stage, connection_is_current=provider.current,
        # The checked stage excludes all other files, including workflows.
        verified_workflow_classifier=lambda _snapshot: False)
    freezer = make_grant_bundle_freezer(root / "runner", root / "private-stage", root / "runner",
        confirmed_stage_authorizer=lambda grant, snapshot: store.confirmed_stage(grant, snapshot))
    def freeze(grant, payload):
        frozen = freezer(grant, payload)
        def verify():
            try:
                verify_frozen_bundle(root / "runner", root / "private-stage", run_id=grant["run_id"],
                    attempt_id=payload["attempt_id"], baseline_bundle=root / "baseline.bundle",
                    expected_baseline_sha256=config["baseline_sha256"],
                    commit=frozen["advertised_commit"], image_id=GIT_IMAGE_ID)
            except Exception:
                # The verifier writes its one-shot result; status stays unknown
                # on any error. Never schedule a second verifier or provider write.
                pass
        threading.Thread(target=verify, daemon=True, name="exp139-bundle-verifier").start()
        return frozen
    store.stage_freezer = freeze
    git = GitHubGitTransport(REPOSITORY, root / "source", config["baseline"], provider.token,
                              require_verified_stage=True)
    budget = WriteBudget(host / "write-budget.sqlite", GitHubMediatedTransport(git, rest), store)
    transport = JournaledTransport(budget, host / "provider-attempts.jsonl",
                                    host / "push-diagnostics.jsonl")
    authority = RunGrantAuthority(host / "authority.sqlite", connection_authorizer=provider.authorize)
    return root, config, store, transport, authority, rest


def services(root):
    root, config = configuration(root)
    approved(root)
    root, config, store, transport, authority, _rest = composition(root)
    lease = LeaseService(root / "host/lease", mediator=store,
                         mediation_authority=authority.authorize_lease)
    mediator = MediationHTTPService(store, transport)
    serve_services(lease, mediator, root / "host", repository=REPOSITORY,
                   connection_id=config["connection_id"], connection_generation=1)


def runner(root):
    root, config = configuration(root)
    approved(root)
    root, config, store, transport, authority, rest = composition(root)
    inputs = json.loads((root / "flow-input/inputs.json").read_bytes())
    flow = json.loads((root / "flow-input/success.json").read_bytes())
    form = json.loads(next(node for node in flow["data"]["nodes"] if node["id"] == "requirements")
                      ["data"]["node"]["template"]["requirements_json"]["value"])
    selected = {}
    for case, task in inputs["tasks"].items():
        body = {"task": json.dumps({"task": task, "frozen_issue": inputs["snapshot"]}, sort_keys=True,
                                  ensure_ascii=False), "model": "gpt-6-luna", "effort": "low",
                "skill_ref": {key: config["skill"][key] for key in ("skill_id", "revision_id", "tree_hash")},
                "output_requirements": requirements(form), "output_retries": 1}
        selected[request_digest(body)] = case
    def authorize():
        return authority.approve(invocation_id=IDENTITY + "-success", repository=REPOSITORY,
            branch=BRANCH, operations={"git_push", "pr_create"}, reviewed_by=IDENTITY + "-owner",
            connection_id=config["connection_id"], connection_generation=1, base_branch=config["base"])
    def artifact(record, handoff_id):
        attempts = list((root / "private-stage" / record["run_id"]).glob("*/result.json"))
        if len(attempts) != 1:
            raise ValueError("single_verified_attempt_required")
        frozen = json.loads(attempts[0].read_bytes())
        with closing(store._connect()) as db:
            grant = dict(db.execute("SELECT * FROM grants WHERE grant_id=?", (handoff_id,)).fetchone())
        return store.verified_stage_resolver(grant, REPOSITORY,
            {"commit": frozen["advertised_commit"], "stage_attempt_id": attempts[0].parent.name})
    def readback(repository, number):
        raw = rest._call("GET", f"/repos/{repository}/pulls/{number}", None,
                         config["connection_id"], 1)
        return {"number": raw["number"], "draft": raw["draft"], "title": raw["title"],
                "body": raw["body"], "base": raw["base"]["ref"],
                "head": {"repository": raw["head"]["repo"]["full_name"],
                         "branch": raw["head"]["ref"], "sha": raw["head"]["sha"]}}
    def describe(record):
        issue = inputs["snapshot"]["context"]["issue"]
        return "EXP-139 bounded issue report", (
            "Bounded imported Langflow success demonstration.\n\nIssue: " + issue["url"] +
            "\nFrozen issue: " + inputs["snapshot"]["snapshot_id"] +
            "\nRun: " + record["run_id"] + "\nNo claim of arbitrary issue implementation.\n")
    controller = PublicationController(store, lifetime_seconds=600, artifact_resolver=artifact,
        transport=transport, readback=readback, describe=describe)
    engine = BoundRunner(root / "runner", root / "skill-store", root / "source",
        approved_requests=selected, authorization_factory=authorize, max_model_turns=4,
        git_workspace=True, supervise_containers=True, lease_service=root / "host/lease",
        github_authority=authority, mediator_state=root / "host/mediator", publication_controller=controller)
    server = serve(engine, port=8779)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=("services", "runner"))
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    try:
        (services if args.role == "services" else runner)(args.state.resolve())
    except Exception as failure:
        print(json.dumps({"status": "runtime_refused", "error_class": type(failure).__name__}))
        raise SystemExit(1)
