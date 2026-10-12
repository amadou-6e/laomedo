"""Prepare fresh bounded state from retained inputs; never launch a model or write GitHub."""
import ast
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from experiments.exp139.prepare import ROOT, IDENTITY, BRANCH, LANGFLOW, save
from laomedo.git_workspace import _git_environment, _bounded_git
from laomedo.skill_store import SkillStore
from laomedo.siwc_auth import _outside_git


def prepare(root):
    root = _outside_git(root)
    if root.name != "laomedo-" + IDENTITY:
        raise ValueError("fresh_campaign_root_required")
    prior = root.parent / "laomedo-exp139-20261011-a"
    ledger = json.loads((prior / "runner/turn-ledger.json").read_bytes())
    if ledger != {"attempted_turns": 7, "max_authorized_turns": 10}:
        raise ValueError("prior_ledger_changed")
    budget = prior / "host/write-budget.sqlite"
    with closing(sqlite3.connect("file:" + budget.as_posix() + "?mode=ro", uri=True)) as db:
        assert [r[0] for r in db.execute("SELECT operation FROM attempts")] == ["git_push"]
    with closing(sqlite3.connect("file:" + (prior / "host/mediator/mediator.sqlite").as_posix() + "?mode=ro", uri=True)) as db:
        assert db.execute("SELECT COUNT(*) FROM grants WHERE revoked_at IS NULL").fetchone()[0] == 0
    with closing(sqlite3.connect("file:" + (prior / "host/bindings.sqlite").as_posix() + "?mode=ro", uri=True)) as db:
        consumed = [r[0] for r in db.execute("SELECT digest FROM consumed ORDER BY digest")]
    config = json.loads((prior / "config.json").read_bytes())
    bundle = (prior / "baseline.bundle").read_bytes()
    assert sha256(bundle).hexdigest() == config["baseline_sha256"]
    inputs = json.loads((prior / "flow-input/inputs.json").read_bytes())
    inputs["tasks"]["success"] = ("AMENDMENT-08 fresh campaign; preserve previous evidence. " +
        inputs["tasks"]["success"].replace("exp139-20261011-a", BRANCH))
    root.mkdir(exist_ok=False)
    (root / "baseline.bundle").write_bytes(bundle)
    for directory in ("source", "runner", "host", "private-stage", "flow-input"):
        (root / directory).mkdir()
    save(root / "runner/turn-ledger.json", ledger)
    with tempfile.TemporaryDirectory(prefix="exp139-amend08-git-") as home:
        for args in (("init", "--template=", "--quiet"),
                     ("fetch", "--no-tags", str(root / "baseline.bundle"), "refs/heads/laomedo-read"),
                     ("checkout", "--quiet", "-b", config["base"], config["baseline"])):
            result = _bounded_git(["git", "-c", "core.hooksPath=" + home,
                "-C", str(root / "source"), *args], _git_environment(home))
            if result.returncode:
                raise ValueError("baseline_checkout_failed")
    skill = SkillStore(root / "skill-store").import_skill("live-report", ROOT / "examples/langflow-workgraph-live/skill")
    assert all(skill[key] == config["skill"][key] for key in ("skill_id", "revision_id", "tree_hash"))
    config.update(identity=IDENTITY, branch=BRANCH, startup_amendment="AMENDMENT-08",
        previous_consumed=consumed, prior_turns=7, prior_write_budget=str(budget))
    # Preserve the approved host connection reference, which resolves GH_LAOMEDO
    # in place. No token value or login file is copied.
    save(root / "config.json", config)
    save(root / "flow-input/inputs.json", inputs)
    tree = ast.parse((ROOT / "experiments/exp139/prepare.py").read_text())
    script = next(node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "script" for target in node.targets))
    build = subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none", "--user", "1000:1000",
        "--mount", f"type=bind,source={ROOT},target=/work,readonly",
        "--mount", f"type=bind,source={root / 'flow-input'},target=/input",
        "--env", "PYTHONPATH=/work", "--entrypoint", "python", LANGFLOW, "-c", script],
        capture_output=True, timeout=60)
    if build.returncode:
        raise ValueError("graph_export_failed")
    save(root / "preparation.json", {"identity": IDENTITY, "startup_amendment": "AMENDMENT-08",
        "model_turns": 0, "github_writes": 0, "prior_used_turns": 7, "prior_push_attempts": 1,
        "prior_draft_pr_attempts": 0, "frozen_inputs_from": "AMENDMENT-07",
        "graph_hashes": {case: sha256((root / f"flow-input/{case}.json").read_bytes()).hexdigest()
            for case in inputs["tasks"]}})
    return {"prepared": True, "activated": False, "used_turns": 7, "cumulative_cap": 10,
            "prior_push_attempts": 1, "additional_push_allowance": 1, "copied_credentials": False}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().state.resolve())))
