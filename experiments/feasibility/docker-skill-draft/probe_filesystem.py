"""Credential-free Docker Skill Draft failure matrix for issue 146."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "122"))
from probe_container_codex_boundary import CONFIG, container_command
from probe_codex_edit import validate_draft
from probe_draft_guards import (BASE_SKILL, inventory, policy_ref, restore,
                                snapshot, tree_hash)


def run(root: Path, command: str, sandboxed: bool = True) -> dict:
    result = subprocess.run(container_command(root, command, sandboxed),
                            capture_output=True, text=True, timeout=45,
                            encoding="utf-8", errors="replace")
    return {"exit_code": result.returncode,
            "permission_denied": any(word in result.stderr for word in
                                     ("Permission denied", "Read-only file system")),
            "timeout": result.returncode == 124,
            "error_excerpt": result.stderr[:120].replace(str(root), "<scratch>")}


def main() -> None:
    workspace = Path(__file__).resolve().parents[3]
    scratch_parent = (workspace.parent / "probe-artifacts.local").resolve()
    if not scratch_parent.is_relative_to(workspace.parent.resolve()):
        raise ValueError("scratch_root_invalid")
    scratch_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="laomedo-docker-filesystem-",
                                     dir=scratch_parent) as name:
        root = Path(name).resolve()
        if root == scratch_parent or not root.is_relative_to(scratch_parent):
            raise ValueError("scratch_path_invalid")
        draft, canonical, store = (root / part for part in
                                   ("draft", "canonical", "store"))
        for path in (draft, canonical, store):
            path.mkdir()
        (root / "config.toml").write_text(CONFIG, encoding="utf-8")
        (draft / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
        (canonical / "SKILL.md").write_text(BASE_SKILL, encoding="utf-8")
        sentinel = store / "sentinel.txt"
        sentinel.write_text("STORE-ORIGINAL", encoding="utf-8")
        base_hash = tree_hash(inventory(canonical))
        report = {"issue": 146, "model_calls": 0, "credential_used": False,
                  "policy_ref": policy_ref(), "image": "laomedo-codex-boundary:0.159.2"}

        report["store_positive_control"] = run(
            root, "printf CONTROL > /store/control.txt", sandboxed=False)
        report["allowed_edit"] = run(
            root, "printf '\nExample: answer amber for the fixed case.\n' >> /draft/SKILL.md")
        allowed_validation = validate_draft(canonical, draft, base_hash)
        report["allowed_result"] = {
            "changed_paths": allowed_validation["changed_paths"],
            "violations": allowed_validation["violations"],
            "patch_available": bool(allowed_validation["patch"]),
            "fixed_case_passed": allowed_validation["draft_evaluation"]["passed"],
            "draft_hash_differs": allowed_validation["draft_hash"] != base_hash,
        }
        report["store_forbidden"] = run(
            root, "printf FORBIDDEN > /store/sentinel.txt")
        report["canonical_forbidden"] = run(
            root, "printf FORBIDDEN > /canonical/SKILL.md")
        report["traversal_forbidden"] = run(
            root, "printf FORBIDDEN > /draft/../store/sentinel.txt")

        report["symlink_create"] = run(
            root, "ln -s /store/sentinel.txt /draft/escape-link", sandboxed=False)
        report["symlink_created"] = (
            run(root, "test -L /draft/escape-link", sandboxed=False)["exit_code"] == 0)
        if report["symlink_created"]:
            report["symlink_forbidden"] = run(
                root, "printf FORBIDDEN > /draft/escape-link")
            try:
                inventory(draft)
                report["symlink_rejected_by_inventory"] = False
            except ValueError:
                report["symlink_rejected_by_inventory"] = True
        else:
            report["symlink_forbidden"] = None
            report["symlink_rejected_by_inventory"] = None
        report["symlink_removed"] = (
            run(root, "rm -f /draft/escape-link", sandboxed=False)["exit_code"] == 0)

        report["script_write"] = run(
            root, "printf 'echo synthetic' > /draft/extra.sh")
        script_validation = validate_draft(canonical, draft, base_hash)
        report["script_rejected_by_policy"] = bool(script_validation["violations"])
        (draft / "extra.sh").unlink(missing_ok=True)

        report["partial_failure"] = run(root,
            "printf '\nExample: partial change.\n' >> /draft/SKILL.md; "
            "printf FORBIDDEN > /store/sentinel.txt")
        report["partial_draft_changed"] = "Example: partial change." in (
            draft / "SKILL.md").read_text(encoding="utf-8")
        report["partial_ineligible"] = (
            report["partial_failure"]["exit_code"] != 0
            and report["partial_draft_changed"])

        report["timeout_case"] = run(root,
            "timeout 1 sh -c 'printf \"\\nExample: timed partial.\\n\" "
            ">> /draft/SKILL.md; sleep 5'")
        report["timeout_partial_present"] = "Example: timed partial." in (
            draft / "SKILL.md").read_text(encoding="utf-8")
        report["timeout_ineligible"] = (
            report["timeout_case"]["timeout"] and report["timeout_partial_present"])

        pre_restore_hash = tree_hash(inventory(draft))
        try:
            restore(root / "missing", draft, pre_restore_hash, root)
            report["missing_snapshot_refused"] = False
        except ValueError:
            report["missing_snapshot_refused"] = (
                tree_hash(inventory(draft)) == pre_restore_hash)
        frozen = root / "snapshot"
        frozen_hash = snapshot(draft, frozen)
        (frozen / "SKILL.md").write_text("CORRUPT", encoding="utf-8")
        try:
            restore(frozen, draft, frozen_hash, root)
            report["corrupt_snapshot_refused"] = False
        except ValueError:
            report["corrupt_snapshot_refused"] = (
                tree_hash(inventory(draft)) == pre_restore_hash)

        (canonical / "SKILL.md").write_text(BASE_SKILL + "\nnew revision\n",
                                            encoding="utf-8")
        conflict = validate_draft(canonical, draft, base_hash,
                                  current_revision="2")
        report["concurrent_base_refused"] = (
            "canonical_changed" in conflict["violations"]
            and "base_revision_conflict" in conflict["violations"])
        report["store_sentinel_unchanged"] = (
            sentinel.read_text(encoding="utf-8") == "STORE-ORIGINAL")
        report["all_required_checks_passed"] = all([
            report["store_positive_control"]["exit_code"] == 0,
            report["allowed_edit"]["exit_code"] == 0,
            report["allowed_result"]["changed_paths"] == ["SKILL.md"],
            report["allowed_result"]["draft_hash_differs"],
            not report["allowed_result"]["violations"],
            report["allowed_result"]["patch_available"],
            report["allowed_result"]["fixed_case_passed"],
            report["store_forbidden"]["permission_denied"],
            report["canonical_forbidden"]["permission_denied"],
            report["traversal_forbidden"]["permission_denied"],
            report["symlink_created"],
            bool(report["symlink_forbidden"] and
                 report["symlink_forbidden"]["permission_denied"]),
            report["symlink_rejected_by_inventory"],
            report["symlink_removed"],
            report["script_write"]["exit_code"] == 0,
            report["script_rejected_by_policy"],
            report["partial_failure"]["permission_denied"],
            report["partial_ineligible"],
            report["timeout_ineligible"],
            report["missing_snapshot_refused"],
            report["corrupt_snapshot_refused"],
            report["concurrent_base_refused"],
            report["store_sentinel_unchanged"],
        ])
        print(json.dumps(report, indent=2))
        if not report["all_required_checks_passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
