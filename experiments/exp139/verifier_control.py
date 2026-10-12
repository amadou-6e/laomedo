"""Reverify a copied failed capture with a synthetic active binding, no login."""
import json
from pathlib import Path
import shutil
import tempfile

from experiments.exp139.runtime import verify_attempt


def probe(state):
    run_id = "d5168375-57e8-4c1e-9cf5-a71e9d49b0d7"
    record = json.loads((state / "runner/runs" / run_id / "record.json").read_bytes())
    captures = list((state / "private-stage" / run_id).glob("*/result.json"))
    assert len(captures) == 1
    attempt_id = captures[0].parent.name
    with tempfile.TemporaryDirectory(prefix="exp139-verifier-control-") as directory:
        root = Path(directory)
        run = root / "runner/runs" / run_id
        (run / "workspace").mkdir(parents=True)
        owner = record["container_ownership"]
        binding = {"run_id": run_id, "status": "running", "workspace_mode": "git",
            "git_baseline": record["git_baseline"], "github_scope": record["github_scope"],
            "container_ownership": {**{key: owner[key] for key in ("name", "launch_token", "grant_id")},
                                    "supervised": True, "cleanup_verified": False}}
        (run / "record.json").write_text(json.dumps(binding))
        target = root / "private-stage" / run_id / attempt_id
        target.mkdir(parents=True)
        for name in ("input.bundle", "result.json"):
            shutil.copyfile(captures[0].parent / name, target / name)
        shutil.copyfile(state / "baseline.bundle", root / "baseline.bundle")
        config = json.loads((state / "config.json").read_bytes())
        result = verify_attempt(root, config, run_id, attempt_id)
        container = result.get("container", {})
        observed = {"status": result["status"],
            "container_status": container.get("status"),
            "cleanup_verified": container.get("cleanup_verified"),
            "limits_verified": container.get("limits_verified"),
            "success_marker_seen": container.get("success_marker_seen"),
            "commit": result["commit"], "image_id": result["image_id"],
            "binding": "synthetic_active_copy_of_retained_capture",
            "model_turns": 0, "provider_writes": 0, "real_login": False}
        assert observed["status"] == "verified" and observed["cleanup_verified"] is True
        return observed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    result = probe(parser.parse_args().state)
    Path(__file__).with_name("VERIFY-CONTROL.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
