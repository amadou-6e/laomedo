"""Historical EXP-139 host composition, retained for its pinned observation.

This old protocol passes a retired global cap to its injected runner. It is not
a supported current-runtime launcher. Reproduce only against the observation's
pinned source; a new campaign requires a separately reviewed verification
harness migration. Do not restore that cap to normal runners.

Never starts merely by importing.

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

from experiments.exp139.bindings import BoundRunner; from experiments.exp139.bindings import MailboxAppServer; from experiments.exp139.bindings import request_digest
from experiments.exp139.prepare import connection; from experiments.exp139.prepare import IDENTITY; from experiments.exp139.prepare import REPOSITORY; from experiments.exp139.prepare import BRANCH
from laomedo.host.publication.bundle.stage import verify_frozen_bundle; from laomedo.host.publication.bundle.stage import _read_frozen
from laomedo.github.transport.git.transport import GitHubGitTransport; from laomedo.github.transport.git.transport import GitHubMediatedTransport
from laomedo.host.mediation.store import MediationStore; from laomedo.host.mediation.errors import KnownRejected
from laomedo.github.transport.rest.transport import GitHubRestTransport
from laomedo.host.host_services import serve_services
from laomedo.host.leases.service import LeaseService
from laomedo.agents.runtime.constants import GIT_IMAGE_ID; from laomedo.agents.runtime.serving import RunnerServer as serve
from experiments.turn_harness import VerificationLocalRunner as LocalRunner
from laomedo.host.mediation.authority import RunGrantAuthority
from laomedo.host.mediation.service import MediationHTTPService; from laomedo.host.mediation.service import JournaledTransport
from laomedo.agents.contracts.output import requirements
from laomedo.host.publication.controller import PublicationController
from laomedo.host.credentials.siwc.utils import _outside_git
from laomedo.host.publication.verified.utils import make_grant_bundle_freezer; from laomedo.host.publication.verified.utils import make_grant_stage_resolver; from laomedo.host.publication.verified.utils import stage_verified_git

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = "experiments/exp139/issue-report.md"


def verify_attempt(root, config, run_id, attempt_id):
    # A freeze receipt has no commit. Resolve it from the checksum-checked
    # private bundle header before invoking the one-shot Docker verifier.
    _, frozen = _read_frozen(root / "runner", root / "private-stage", run_id, attempt_id)
    return verify_frozen_bundle(root / "runner", root / "private-stage",
        run_id=run_id, attempt_id=attempt_id, baseline_bundle=root / "baseline.bundle",
        expected_baseline_sha256=config["baseline_sha256"],
        commit=frozen["advertised_commit"], image_id=GIT_IMAGE_ID)


def configuration(root):
    root = _outside_git(root)
    config = json.loads((root / "config.json").read_bytes())
    if config.get("identity") == "langflow-demo-20261012-c":
        if (config.get("repository") != REPOSITORY or config.get("branch") != "langflow-demo-20261012-c" or
                config.get("turn_cap") != 4 or config.get("runner_port") != 8779 or
                config.get("handoff_seconds") != 600 or any(key in config for key in
                ("prior_turns", "prior_write_budget", "previous_consumed"))):
            raise ValueError("frozen_configuration_required")
        return root, config
    if (config.get("identity") != IDENTITY or config.get("repository") != REPOSITORY or
            config.get("branch") != BRANCH or config.get("turn_cap") != 10 or
            config.get("runner_port") != 8779 or config.get("handoff_seconds") != 600 or
            config.get("recovery") != "AMENDMENT-03" or
            config.get("startup_amendment") != "AMENDMENT-08" or
            config.get("prior_turns") != 7 or
            config.get("prior_write_budget") != str(root.parent / "laomedo-exp139-20261011-a/host/write-budget.sqlite")):
        raise ValueError("frozen_configuration_required")
    return root, config


def approved(root):
    """Require concrete activation and exact-source review records, not a CLI flag."""
    _, config = configuration(root)
    source = __import__("subprocess").check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    manifest = root / "manifest.json"
    approval = json.loads((root / "activation.json").read_bytes())
    expected = {"identity": config["identity"], "source_sha": source,
                "manifest_sha256": sha256(manifest.read_bytes()).hexdigest(),
                "configuration_approved": True, "review_verdict": "approve"}
    if approval != expected:
        raise ValueError("exact_activation_review_required")
    process = __import__("subprocess")
    if process.check_output(["git", "-C", str(ROOT), "status", "--porcelain"]).strip():
        raise ValueError("exact_clean_source_required")
    manifest_path = "DEMO-MANIFEST.json" if config["identity"].startswith("langflow-demo-") else "MANIFEST.json"
    committed = process.check_output(["git", "-C", str(ROOT), "show", "HEAD:experiments/exp139/" + manifest_path])
    if manifest.read_bytes() != committed:
        raise ValueError("committed_manifest_required")
    frozen = json.loads(manifest.read_bytes())
    for relative, digest in frozen["source_hashes"].items():
        if sha256((ROOT / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen_source_changed")
    for relative, digest in frozen["input_hashes"].items():
        if sha256((root / relative).read_bytes()).hexdigest() != digest:
            raise ValueError("frozen_input_changed")


class WriteBudget:
    """Durable attempt budget; reserve before provider dispatch, never reset."""
    def __init__(self, path, transport, store, *, prior_write_budget=None, branch=BRANCH):
        self.path, self.transport, self.store = path, transport, store
        self.branch = branch
        self.prior_write_budget = prior_write_budget
        self._check_prior_budget()
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (operation TEXT PRIMARY KEY)")

    def _check_prior_budget(self):
        if self.prior_write_budget is not None:
            path = Path(self.prior_write_budget)
            with closing(sqlite3.connect("file:" + path.as_posix() + "?mode=ro", uri=True)) as db:
                attempts = [row[0] for row in db.execute("SELECT operation FROM attempts ORDER BY operation")]
            if attempts != ["git_push"]:
                raise KnownRejected("experiment_prior_budget_changed")

    def __call__(self, repository, operation, payload, **binding):
        self._check_prior_budget()
        if repository != REPOSITORY or operation not in {"git_push", "pr_create"}:
            raise KnownRejected("experiment_operation_denied")
        if operation == "git_push" and payload.get("branch") != self.branch:
            raise KnownRejected("experiment_branch_denied")
        if operation == "pr_create":
            with closing(self.store._connect()) as db:
                rows = db.execute("SELECT h.phase FROM publication_handoffs h JOIN grants g "
                    "ON g.grant_id=h.grant_id WHERE g.repository=? AND g.branch=? "
                    "AND h.phase='publication_pending'",
                    (REPOSITORY, self.branch)).fetchall()
            if (len(rows) != 1 or rows[0]["phase"] != "publication_pending" or
                    payload.get("head") != self.branch or payload.get("draft") is not True):
                raise KnownRejected("experiment_publisher_lane_required")
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            try:
                db.execute("INSERT INTO attempts VALUES (?)", (operation,))
            except sqlite3.IntegrityError:
                raise KnownRejected("experiment_write_budget_consumed") from None
        return self.transport(repository, operation, payload, **binding)


def composition(root, *, budget_class=WriteBudget):
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
                raise KnownRejected("bounded_report_artifact_required")
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
                verify_attempt(root, config, grant["run_id"], payload["attempt_id"])
            except Exception:
                # The verifier writes its one-shot result; status stays unknown
                # on any error. Never schedule a second verifier or provider write.
                pass
        threading.Thread(target=verify, daemon=True, name="exp139-bundle-verifier").start()
        return frozen
    store.stage_freezer = freeze
    git = GitHubGitTransport(REPOSITORY, root / "source", config["baseline"], provider.token,
                              require_verified_stage=True)
    budget = budget_class(host / "write-budget.sqlite", GitHubMediatedTransport(git, rest), store,
                         prior_write_budget=config.get("prior_write_budget"), branch=config["branch"])
    transport = JournaledTransport(budget, host / "provider-attempts.jsonl",
                                    host / "push-diagnostics.jsonl")
    authority = RunGrantAuthority(host / "authority.sqlite", connection_authorizer=provider.authorize)
    return root, config, store, transport, authority, rest


def services(root, *, startup_check=approved, composition_factory=composition):
    root, config = configuration(root)
    startup_check(root)
    root, config, store, transport, authority, _rest = composition_factory(root)
    lease = LeaseService(root / "host/lease", mediator=store,
                         mediation_authority=authority.authorize_lease)
    mediator = MediationHTTPService(store, transport)
    ordinary = LeaseService(root / "host/nonpublishing-lease")
    threading.Thread(target=ordinary.serve, daemon=True,
                     name="exp139-nonpublishing-supervisor").start()
    serve_services(lease, mediator, root / "host", repository=REPOSITORY,
                   connection_id=config["connection_id"], connection_generation=1)


def runner(root, *, startup_check=approved, composition_factory=composition, engine_class=BoundRunner, port=8779):
    root, config = configuration(root)
    startup_check(root)
    root, config, store, transport, authority, rest = composition_factory(root)
    inputs = json.loads((root / "flow-input/inputs.json").read_bytes())
    flow = json.loads((root / "flow-input/success.json").read_bytes())
    form = json.loads(next(node for node in flow["data"]["nodes"] if node["id"] == ("contract" if config["identity"].startswith("langflow-demo-") else "requirements"))
                      ["data"]["node"]["template"]["requirements_json"]["value"])
    selected = {}
    for case, task in inputs["tasks"].items():
        body = {"task": json.dumps({"task": task, "frozen_issue": inputs["snapshot"]}, sort_keys=True,
                                  ensure_ascii=False), "model": "gpt-6-luna", "effort": "low",
                "skill_ref": {key: config["skill"][key] for key in ("skill_id", "revision_id", "tree_hash")},
                "output_requirements": requirements(form), "output_retries": 1}
        selected[request_digest(body)] = case
    def authorize(branch=None):
        return authority.approve(invocation_id=config["identity"] + "-success-" +
            (branch or next(digest for digest, case in selected.items() if case == "success")), repository=REPOSITORY,
            branch=branch or config["branch"], operations={"git_push", "pr_create"}, reviewed_by=config["identity"] + "-owner",
            connection_id=config["connection_id"], connection_generation=1, base_branch=config["base"])
    def artifact(record, handoff_id):
        attempts = list((root / "private-stage" / record["run_id"]).glob("*/result.json"))
        if len(attempts) != 1:
            raise ValueError("single_verified_attempt_required")
        _, frozen = _read_frozen(root / "runner", root / "private-stage",
                                 record["run_id"], attempts[0].parent.name)
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
    engine = engine_class(root / "runner", root / "skill-store", root / "source",
        approved_requests=selected, authorization_factory=authorize, max_model_turns=config["turn_cap"],
        nonpublishing_lease_service=root / "host/nonpublishing-lease",
        binding_state=root / "host/bindings.sqlite", seed_consumed=config.get("previous_consumed", {}),
        transport=MailboxAppServer,
        git_workspace=True, supervise_containers=True, lease_service=root / "host/lease",
        github_authority=authority, mediator_state=root / "host/mediator", publication_controller=controller)
    server = serve(engine, port=port)
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
