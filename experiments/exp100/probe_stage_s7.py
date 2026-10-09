"""One-shot, credential-free Docker check of the product bundle stage."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from laomedo.bundle_ingest import HANDOFF_NAME, freeze_run_bundle
from laomedo.bundle_stage import (BundleStageError, PINNED_IMAGE_ID, _run,
                                  _single_bundle_commit, verify_frozen_bundle)


IDENTITY = "exp100-s7-20261009-a"
HERE = Path(__file__).resolve().parent
EVIDENCE = HERE / "observation-s7.json"
PENDING = HERE / "observation-s7.json.pending"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("GIT_", "GH_")):
            env.pop(key)
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT="0", GIT_NO_REPLACE_OBJECTS="1",
               GIT_OPTIONAL_LOCKS="0")
    process = subprocess.run(["git", "-C", str(repo), *args], env=env,
                             capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise RuntimeError("git_failed:" + args[0])
    return process.stdout.strip()


def fixture(root: Path, suffix: str) -> dict:
    trusted = root / ("trusted-" + suffix)
    agent = root / ("agent-" + suffix)
    runner = root / ("runner-" + suffix)
    private = root / ("private-" + suffix)
    trusted.mkdir()
    private.mkdir()
    git(trusted, "init", "--quiet")
    (trusted / "base.txt").write_bytes(b"synthetic baseline\n")
    git(trusted, "add", "base.txt")
    git(trusted, "-c", "user.name=Test", "-c",
        "user.email=test@example.invalid", "commit", "--quiet", "-m", "base")
    baseline = git(trusted, "rev-parse", "HEAD")
    git(root, "clone", "--quiet", "--no-local", str(trusted), str(agent))
    git(agent, "checkout", "--quiet", "-b", "run-branch")
    (agent / "candidate.txt").write_bytes(b"synthetic candidate\n")
    git(agent, "add", "candidate.txt")
    git(agent, "-c", "user.name=Agent", "-c",
        "user.email=agent@example.invalid", "commit", "--quiet", "-m",
        "candidate")
    commit = git(agent, "rev-parse", "HEAD")
    workspace = runner / "runs" / ("run-" + suffix) / "workspace"
    workspace.mkdir(parents=True)
    (workspace.parent / "record.json").write_text(json.dumps({
        "run_id": "run-" + suffix, "status": "completed", "workspace_mode": "git",
        "git_baseline": baseline, "github_scope": {
            "repository": "example/disposable", "branch": "run-branch"}
    }), encoding="utf-8", newline="\n")
    git(agent, "bundle", "create", str(workspace / HANDOFF_NAME),
        "refs/heads/run-branch")
    baseline_bundle = root / ("baseline-" + suffix + ".bundle")
    git(trusted, "bundle", "create", str(baseline_bundle), "HEAD")
    frozen = freeze_run_bundle(runner, private, run_id="run-" + suffix,
                               attempt_id="attempt-" + suffix)
    return {"trusted": trusted, "runner": runner, "private": private,
            "baseline": baseline, "commit": commit,
            "baseline_bundle": baseline_bundle,
            "baseline_sha256": digest(baseline_bundle.read_bytes()),
            "source_sha256": frozen["bundle_sha256"],
            "run_id": "run-" + suffix, "attempt_id": "attempt-" + suffix}


def verify_export(root: Path, positive: dict, output: Path) -> dict:
    stage = root / "imported.git"
    stage.mkdir()
    git(stage, "init", "--bare", "--quiet")
    git(stage, "bundle", "unbundle", str(positive["baseline_bundle"]))
    git(stage, "bundle", "unbundle", str(output))
    kind = git(stage, "cat-file", "-t", positive["commit"])
    git(stage, "fsck", "--strict", "--no-reflogs", positive["commit"])
    git(stage, "merge-base", "--is-ancestor", positive["baseline"],
        positive["commit"])
    advertised = _single_bundle_commit(output.read_bytes(),
                                       "refs/heads/validated")
    return {"commit_matches": advertised == positive["commit"],
            "object_type": kind, "fsck": "passed", "ancestry": "passed"}


def run_once(output: dict, checkpoint) -> None:
    output.update(image_id=PINNED_IMAGE_ID, provider_calls=0,
                  model_turns=0, cases={})
    with tempfile.TemporaryDirectory(prefix="laomedo-exp100-s7-") as temporary:
        root = Path(temporary)
        positive = fixture(root, "positive")
        output["cases"]["positive"] = {
            "baseline": positive["baseline"], "commit": positive["commit"],
            "source_sha256": positive["source_sha256"],
            "baseline_sha256": positive["baseline_sha256"]}
        created: list[str] = []

        def traced_docker(args: list[str], timeout: float = 30):
            if args[:2] == ["docker", "create"]:
                created.append(args[args.index("--name") + 1])
            return _run(args, timeout)

        try:
            result = verify_frozen_bundle(
                positive["runner"], positive["private"],
                run_id=positive["run_id"], attempt_id=positive["attempt_id"],
                baseline_bundle=positive["baseline_bundle"],
                expected_baseline_sha256=positive["baseline_sha256"],
                commit=positive["commit"], image_id=PINNED_IMAGE_ID,
                docker=traced_docker)
            output["cases"]["positive"]["result"] = result
        except Exception as error:
            output["cases"]["positive"]["error_class"] = type(error).__name__
        output["cases"]["positive"]["create_count"] = len(created)
        presence = []
        for name in created:
            try:
                presence.append(_run(["docker", "inspect", name],
                                     10).returncode == 0)
            except Exception:
                presence.append(None)
        output["cases"]["positive"]["container_present_after"] = presence
        checkpoint()
        verified = (positive["private"] / positive["run_id"] /
                    positive["attempt_id"] / "verified.bundle")
        if verified.is_file():
            output["cases"]["positive"]["output_sha256"] = digest(
                verified.read_bytes())
            try:
                output["cases"]["positive"]["independent"] = verify_export(
                    root, positive, verified)
            except Exception as error:
                output["cases"]["positive"]["independent"] = {
                    "status": "failed", "error_class": type(error).__name__}
            checkpoint()

        negative = fixture(root, "wrong-commit")
        before = len(created)
        try:
            verify_frozen_bundle(
                negative["runner"], negative["private"],
                run_id=negative["run_id"], attempt_id=negative["attempt_id"],
                baseline_bundle=negative["baseline_bundle"],
                expected_baseline_sha256=negative["baseline_sha256"],
                commit=negative["baseline"], image_id=PINNED_IMAGE_ID,
                docker=traced_docker)
            negative_class = "unexpected_accept"
        except BundleStageError as error:
            negative_class = str(error)
        output["cases"]["wrong_commit"] = {
            "result": negative_class, "new_create_count": len(created) - before,
            "verified_output_exists": (negative["private"] /
                negative["run_id"] / negative["attempt_id"] /
                "verified.bundle").exists()}
        checkpoint()

    good = output["cases"]["positive"]
    bad = output["cases"]["wrong_commit"]
    product = good.get("result", {})
    container = product.get("container", {})
    independent = good.get("independent", {})
    output["status"] = "passed" if (
        product.get("status") == "verified" and
        product.get("policy_approved") is False and
        container.get("cleanup_verified") is True and
        good["create_count"] == 1 and
        good["container_present_after"] == [False] and
        good.get("output_sha256") is not None and
        good["output_sha256"] == container.get("output_sha256") and
        independent.get("commit_matches") is True and
        independent.get("object_type") == "commit" and
        independent.get("fsck") == "passed" and
        independent.get("ancestry") == "passed" and
        bad["result"] == "candidate_commit_mismatch" and
        bad["new_create_count"] == 0 and
        not bad["verified_output_exists"]
    ) else "failed"



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", required=True)
    args = parser.parse_args()
    del args
    if EVIDENCE.exists() or PENDING.exists():
        raise SystemExit("S7 identity already consumed")
    if git(HERE, "status", "--porcelain", "--untracked-files=all"):
        raise SystemExit("S7 source tree is not clean")
    source_files = [Path("laomedo/bundle_stage.py"),
                    Path("laomedo/bundle_ingest.py"),
                    Path("laomedo/resources/bundle_stage.sh")]
    repo_root = HERE.parents[1]
    source_hashes = {path.as_posix(): digest((repo_root / path).read_bytes())
                     for path in source_files}
    with PENDING.open("xb") as marker:
        marker.write((IDENTITY + "\n").encode("ascii"))
        marker.flush()
        os.fsync(marker.fileno())
    observation = {"identity": IDENTITY, "status": "unknown",
                   "started_at_unix": time.time(),
                   "source_revision": git(HERE, "rev-parse", "HEAD"),
                   "probe_sha256": digest(Path(__file__).read_bytes()),
                   "source_sha256": source_hashes}
    def checkpoint() -> None:
        with PENDING.open("wb") as stream:
            stream.write((json.dumps(observation, indent=2, sort_keys=True) +
                          "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())

    checkpoint()
    try:
        run_once(observation, checkpoint)
    except Exception as error:
        observation["error_class"] = type(error).__name__
    observation["finished_at_unix"] = time.time()
    checkpoint()
    os.replace(PENDING, EVIDENCE)
    print(json.dumps({"identity": IDENTITY, "status": observation["status"]}))
    return 0 if observation["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
