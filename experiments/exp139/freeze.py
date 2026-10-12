"""Freeze prospective source and input identities without credential hashing."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from experiments.exp139.prepare import ROOT, IDENTITY, LANGFLOW, save
from experiments.exp139.runtime import configuration
from laomedo.local_runner import GIT_IMAGE_ID


def freeze(root):
    root, config = configuration(root)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args])
    if git("status", "--porcelain").strip():
        raise ValueError("exact_clean_source_required")
    parent = git("rev-parse", "HEAD").decode().strip()
    paths = git("ls-files", "-z").decode().split("\0")
    sources = [path for path in paths if path.startswith(("laomedo/", "components/",
        "experiments/exp139/", "examples/langflow-workgraph-live/",
        "examples/langflow-workgraph-demo/", "examples/native-codex-node/")) and
        not path.endswith(("MANIFEST.json", "RESULTS.md", "OBSERVATION.json"))]
    manifest = {"identity": IDENTITY, "source_parent": parent, "agent_image": GIT_IMAGE_ID,
        "langflow_image": LANGFLOW, "turn_cap": 10, "push_attempt_cap": 1, "draft_pr_attempt_cap": 1,
        "cumulative_push_attempt_cap": 2, "prior_push_attempts": 1, "prior_used_turns": 7,
        "source_hashes": {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
        "committed_source_hashes": {path: sha256(git("show", "HEAD:" + path)).hexdigest() for path in sources},
        "input_hashes": {path: sha256((root / path).read_bytes()).hexdigest() for path in
            ("config.json", "baseline.bundle", "flow-input/inputs.json", "flow-input/success.json",
             "flow-input/failure.json", "flow-input/rejection.json")}}
    # source_hashes bind actual Windows working bytes; committed_source_hashes
    # explicitly identify Git blobs. CRLF checkout bytes are not called blobs.
    # Inputs contain refs/pins, never credential values or auth files.
    save(root / "manifest.json", manifest)
    save(ROOT / "experiments/exp139/MANIFEST.json", manifest)
    return {"identity": IDENTITY, "model_turns": 0, "github_writes": 0,
            "source_parent": parent, "manifest_sha256": sha256((root / "manifest.json").read_bytes()).hexdigest()}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    print(json.dumps(freeze(parser.parse_args().state.resolve())))
