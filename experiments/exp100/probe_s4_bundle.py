"""One-shot small-fixture Git import with a trusted baseline bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from experiments.exp100 import probe_s4


IDENTITY = "EXP-100-S4-03"
ROOT = probe_s4.ROOT
OBSERVATION = Path(__file__).with_name("observation-s4-03.json")
SCRIPT = Path(__file__).with_name("verify_s4_bundle.sh")
PROTOCOL = Path(__file__).with_name("PROTOCOL-06.md")


def create_baseline_bundle(trusted: Path, destination: Path) -> None:
    probe_s4._git("-C", str(trusted), "bundle", "create", str(destination), "HEAD")
    if destination.stat().st_size > 4 * 1024 * 1024:
        raise RuntimeError("baseline_bundle_oversized")


def preflight(root: Path, baseline_bundle: Path, candidate_bundle: Path,
              baseline: str, commit: str) -> None:
    stage = root / "preflight.git"
    probe_s4._git("init", "--bare", "--quiet", str(stage))
    probe_s4._git("-C", str(stage), "bundle", "unbundle", str(baseline_bundle))
    if probe_s4._git("-C", str(stage), "cat-file", "-t", baseline) != "commit":
        raise RuntimeError("baseline_preflight_failed")
    probe_s4._git("-C", str(stage), "bundle", "unbundle", str(candidate_bundle))
    if probe_s4._git("-C", str(stage), "cat-file", "-t", commit) != "commit":
        raise RuntimeError("candidate_preflight_failed")
    probe_s4._git("-C", str(stage), "fsck", "--strict", "--no-reflogs", commit)
    probe_s4._git("-C", str(stage), "merge-base", "--is-ancestor", baseline,
                  commit)


def run() -> dict:
    image = probe_s4._run(["docker", "image", "inspect", probe_s4.IMAGE_ID,
                           "--format", "{{.Id}}"])
    if image.returncode or image.stdout.strip() != probe_s4.IMAGE_ID:
        raise RuntimeError("pinned_image_unavailable")
    with tempfile.TemporaryDirectory(prefix="laomedo-s4-03-") as directory:
        root = Path(directory)
        trusted, candidate, baseline, commit = probe_s4._fixture(root)
        baseline_bundle = root / "baseline.bundle"
        create_baseline_bundle(trusted, baseline_bundle)
        preflight(root, baseline_bundle, candidate, baseline, commit)
        baseline_hash = hashlib.sha256(baseline_bundle.read_bytes()).hexdigest()
        candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
        case = probe_s4._docker_case(
            "valid_import", ["sh", "/verify.sh", baseline, commit],
            [baseline_bundle, candidate], script_path=SCRIPT,
            trusted_target="/baseline.bundle")
        baseline_unchanged = hashlib.sha256(
            baseline_bundle.read_bytes()).hexdigest() == baseline_hash
        candidate_unchanged = hashlib.sha256(
            candidate.read_bytes()).hexdigest() == candidate_hash
        passed = (case["status"] == "completed" and case["exit_code"] == 0 and
                  case["marker"] == "S4_VERIFIED" and
                  case["cleanup_verified"] and baseline_unchanged and
                  candidate_unchanged and bool(case["container_git_version"]))
        return {"schema_version": 1, "identity": IDENTITY,
                "status": "passed" if passed else "failed",
                "source_commit": probe_s4._git("-C", str(ROOT), "rev-parse", "HEAD"),
                "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                "image_id": probe_s4.IMAGE_ID, "baseline": baseline, "commit": commit,
                "baseline_bundle_sha256": baseline_hash,
                "candidate_bundle_sha256": candidate_hash,
                "baseline_bundle_unchanged": baseline_unchanged,
                "candidate_bundle_unchanged": candidate_unchanged,
                "local_preflight": "passed", "case": case,
                "provider_calls": 0, "model_turns": 0,
                "count_scope": "no provider/model component instantiated"}


def record_once(path: Path, source_commit: str) -> dict:
    with path.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps({"identity": IDENTITY, "status": "unknown",
                                 "source_commit": source_commit}) + "\n")
        output.flush()
        os.fsync(output.fileno())
    try:
        observation = run()
    except Exception as error:
        observation = {"schema_version": 1, "identity": IDENTITY,
                       "status": "unknown", "source_commit": source_commit,
                       "error_class": type(error).__name__}
    pending = path.with_suffix(".pending")
    with pending.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(observation, indent=2, sort_keys=True) + "\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(pending, path)
    return observation


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    if not args.record:
        raise SystemExit("S4-03 requires --record")
    if OBSERVATION.exists():
        raise SystemExit("S4-03 identity already consumed")
    state = probe_s4._run(["git", "status", "--porcelain=v1",
                           "--untracked-files=all"], cwd=ROOT)
    if state.returncode or state.stdout:
        raise SystemExit("source tree must be clean before recording")
    source_commit = probe_s4._git("-C", str(ROOT), "rev-parse", "HEAD")
    observation = record_once(OBSERVATION, source_commit)
    if observation.get("status") != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
