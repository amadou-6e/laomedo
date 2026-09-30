"""Build a policy-checkable candidate from a raw Docker agent workspace."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "122"))
from probe_codex_edit import validate_draft
from probe_draft_guards import policy_ref


EMPTY_RUNTIME_DIRS = frozenset({".agents", ".codex", ".git"})


def materialize(raw: Path, candidate: Path, run_root: Path) -> list[str]:
    root = run_root.resolve(strict=True)
    source = raw.resolve(strict=True)
    target = candidate.resolve(strict=False)
    if (source == root or not source.is_relative_to(root)
            or target == root or not target.is_relative_to(root)
            or candidate.exists() or raw.is_symlink()):
        raise ValueError("candidate_paths_invalid")
    skipped = []
    allowed_file = None
    for entry in raw.iterdir():
        try:
            junction = getattr(entry, "is_junction", lambda: False)
            if entry.is_symlink() or junction():
                raise ValueError("link_or_junction_in_raw_draft")
            if entry.name == "SKILL.md" and entry.is_file():
                allowed_file = entry
            elif entry.name in EMPTY_RUNTIME_DIRS and entry.is_dir():
                if any(entry.iterdir()):
                    raise ValueError("runtime_directory_not_empty")
                skipped.append(entry.name)
            else:
                raise ValueError("unapproved_raw_draft_entry")
        except OSError as exc:
            raise ValueError("unreadable_raw_draft_entry") from exc
    if allowed_file is None:
        raise ValueError("skill_missing")
    candidate.mkdir()
    (candidate / "SKILL.md").write_bytes(allowed_file.read_bytes())
    return sorted(skipped)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate-name", default="candidate")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve(strict=True)
    if args.candidate_name not in ("candidate", "candidate-pinned"):
        raise ValueError("candidate_name_invalid")
    canonical = run_dir / "canonical"
    draft = run_dir / "draft"
    candidate = run_dir / args.candidate_name
    run_summary = json.loads((run_dir / "summary-146.json").read_text(encoding="utf-8"))
    base_hash = run_summary["base_hash"]
    if run_summary["policy_ref"] != policy_ref():
        raise ValueError("policy_ref_changed")
    report = {"policy_ref": policy_ref(), "base_hash": base_hash}
    try:
        report["skipped_empty_runtime_dirs"] = materialize(draft, candidate, run_dir)
        validated = validate_draft(canonical, candidate, base_hash)
        report["changed_paths"] = validated["changed_paths"]
        report["draft_hash"] = validated["draft_hash"]
        report["patch_available"] = bool(validated["patch"])
        report["violations"] = validated["violations"]
        report["fixed_case_passed"] = validated["draft_evaluation"]["passed"]
        report["promotion_eligible"] = (
            not validated["violations"] and bool(validated["patch"])
            and validated["draft_evaluation"]["passed"])
    except ValueError as exc:
        report["promotion_eligible"] = False
        report["blocked"] = str(exc)
    (run_dir / "candidate-summary.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["promotion_eligible"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
