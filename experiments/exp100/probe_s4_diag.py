"""Single-use, credential-free stage diagnostic for the failed S4 import."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from experiments.exp100 import probe_s4


IDENTITY = "EXP-100-S4-02"
ROOT = probe_s4.ROOT
OBSERVATION = Path(__file__).with_name("observation-s4-02.json")
SCRIPT = Path(__file__).with_name("verify_s4_diag.sh")
PROTOCOL = Path(__file__).with_name("PROTOCOL-05.md")


def run() -> dict:
    image = probe_s4._run(["docker", "image", "inspect", probe_s4.IMAGE_ID,
                           "--format", "{{.Id}}"])
    if image.returncode or image.stdout.strip() != probe_s4.IMAGE_ID:
        raise RuntimeError("pinned_image_unavailable")
    with tempfile.TemporaryDirectory(prefix="laomedo-s4-02-") as directory:
        root = Path(directory)
        trusted, bundle, baseline, commit = probe_s4._fixture(root)
        source_before = hashlib.sha256((trusted / "source.txt").read_bytes()).hexdigest()
        bundle_before = hashlib.sha256(bundle.read_bytes()).hexdigest()
        case = probe_s4._docker_case("positive_stage_diagnostic",
                                     ["sh", "/verify.sh", baseline, commit],
                                     [trusted, bundle], script_path=SCRIPT)
        source_unchanged = hashlib.sha256(
            (trusted / "source.txt").read_bytes()).hexdigest() == source_before
        bundle_unchanged = hashlib.sha256(bundle.read_bytes()).hexdigest() == bundle_before
        known_exit = case["exit_code"] is not None
        status = ("diagnosed" if known_exit and case["cleanup_verified"] and
                  source_unchanged and bundle_unchanged else "unknown")
        return {"schema_version": 1, "identity": IDENTITY, "status": status,
                "source_commit": probe_s4._git("-C", str(ROOT), "rev-parse", "HEAD"),
                "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                "probe_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
                "image_id": probe_s4.IMAGE_ID, "baseline": baseline, "commit": commit,
                "bundle_sha256": bundle_before, "source_unchanged": source_unchanged,
                "bundle_unchanged": bundle_unchanged, "case": case,
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
        raise SystemExit("S4-02 requires --record")
    if OBSERVATION.exists():
        raise SystemExit("S4-02 identity already consumed")
    state = probe_s4._run(["git", "status", "--porcelain=v1",
                           "--untracked-files=all"], cwd=ROOT)
    if state.returncode or state.stdout:
        raise SystemExit("source tree must be clean before recording")
    source_commit = probe_s4._git("-C", str(ROOT), "rev-parse", "HEAD")
    observation = record_once(OBSERVATION, source_commit)
    if observation.get("status") != "diagnosed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
