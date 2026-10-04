"""Credential-free skill-byte and workspace-cleanliness probe for EXP-08."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from laomedo.local_runner import LocalRunner, RunnerError
from laomedo.skill_store import SkillStore, SkillStoreError, inventory, tree_hash


SKILL_ID = "exp08-sample"


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


def content_hash(checkout):
    """Hash working files, not Git's mutable index/object database."""
    digest_bytes = hashlib.sha256()
    files = sorted(
        path for path in checkout.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(checkout).parts
    )
    for path in files:
        relative = path.relative_to(checkout).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest_bytes.update(len(relative).to_bytes(8, "big"))
        digest_bytes.update(relative)
        digest_bytes.update(len(data).to_bytes(8, "big"))
        digest_bytes.update(data)
    return "sha256:" + digest_bytes.hexdigest()


def clone(repository, destination, root):
    git("-c", "core.autocrlf=true", "clone", "--no-hardlinks", "-q",
        str(repository), str(destination), cwd=root)
    return destination


def run_case(line_ending, root):
    root.mkdir()
    repository = root / "repository"
    workspace = repository / "source"
    workspace.mkdir(parents=True)
    (workspace / "task.txt").write_bytes(b"synthetic task\n")
    git("init", "-q", cwd=repository)
    git("add", ".", cwd=repository)
    git("-c", "user.name=Probe", "-c", "user.email=probe@example.invalid",
        "commit", "-qm", "fixture", cwd=repository)
    clean_before = git("status", "--porcelain", cwd=repository)

    skill_source = root / "skill-source"
    skill_source.mkdir()
    skill_bytes = b"---" + line_ending + b"name: " + SKILL_ID.encode() + (
        line_ending + b"---" + line_ending + b"Use a synthetic fixture." + line_ending
    )
    (skill_source / "SKILL.md").write_bytes(skill_bytes)
    (skill_source / "notes.txt").write_bytes(b"fixed bytes\r\n")
    store = SkillStore(root / "store")
    revision = store.import_skill(SKILL_ID, skill_source)
    source_inventory = inventory(skill_source)
    source_tree_hash = tree_hash(source_inventory)
    if revision["tree_hash"] != source_tree_hash:
        raise AssertionError("source revision mismatch")

    runner = LocalRunner(root / "state", store.root, workspace,
                         check_docker=False, max_model_turns=0)

    # A real clone first demonstrates the failure mode without an ignore rule.
    risk_checkout = clone(repository, root / "risk-checkout", root)
    runner._materialize(risk_checkout, {
        "skill_id": SKILL_ID, "revision_id": revision["revision_id"],
        "tree_hash": revision["tree_hash"],
    })
    risk_status = git("status", "--porcelain", "--untracked-files=all",
                      cwd=risk_checkout)
    risk_clean_dry_run = git("clean", "-nd", cwd=risk_checkout)
    git("add", "-A", cwd=risk_checkout)
    risk_staged_paths = git("diff", "--cached", "--name-only", cwd=risk_checkout)
    staged_skill = subprocess.run(
        ["git", "show", ":.agents/skills/" + SKILL_ID + "/SKILL.md"],
        cwd=risk_checkout, capture_output=True, check=True,
    ).stdout
    if (".agents/skills/" + SKILL_ID + "/SKILL.md" not in risk_status or
            ".agents/" not in risk_clean_dry_run or
            ".agents/skills/" + SKILL_ID + "/SKILL.md" not in risk_staged_paths):
        raise AssertionError("unprotected checkout did not expose Git risk")
    if staged_skill != skill_bytes.replace(b"\r\n", b"\n"):
        raise AssertionError("Git did not normalize staged skill as expected")

    # The protected agent checkout has its own .git and excludes delivered skills.
    effective_workspace = clone(repository, root / "effective-checkout", root)
    exclude = effective_workspace / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n.agents/skills/\n")
    clean_effective_before = git("status", "--porcelain", cwd=effective_workspace)
    source_workspace_hash = content_hash(repository)
    checkout_before_skill_hash = content_hash(effective_workspace)
    tracked_source_bytes = (repository / "source" / "task.txt").read_bytes()
    checked_out_bytes = (effective_workspace / "source" / "task.txt").read_bytes()
    committed_source_bytes = subprocess.run(
        ["git", "show", "HEAD:source/task.txt"], cwd=effective_workspace,
        capture_output=True, check=True,
    ).stdout
    if (tracked_source_bytes != b"synthetic task\n" or
            committed_source_bytes != b"synthetic task\n" or
            checked_out_bytes != b"synthetic task\r\n"):
        raise AssertionError("clone did not exercise Git line-ending conversion")
    offered = runner._materialize(effective_workspace, {
        "skill_id": SKILL_ID, "revision_id": revision["revision_id"],
        "tree_hash": revision["tree_hash"],
    })
    materialized = effective_workspace / ".agents" / "skills" / SKILL_ID
    effective_inventory = inventory(materialized)
    effective_skill_hash = tree_hash(effective_inventory)
    if effective_inventory != source_inventory or effective_skill_hash != source_tree_hash:
        raise AssertionError("materialized skill bytes differ")
    effective_workspace_hash = content_hash(effective_workspace)
    clean_after_materialization = git("status", "--porcelain", cwd=effective_workspace)
    ignored_skill = git("check-ignore", "-v",
                        ".agents/skills/" + SKILL_ID + "/SKILL.md",
                        cwd=effective_workspace)
    git("add", "-A", cwd=effective_workspace)
    protected_staged_paths = git("diff", "--cached", "--name-only",
                                 cwd=effective_workspace)
    protected_clean_dry_run = git("clean", "-nd", cwd=effective_workspace)
    force_clean_dry_run = git("clean", "-ndx", cwd=effective_workspace)
    if (not ignored_skill or protected_staged_paths or protected_clean_dry_run or
            ".agents/" not in force_clean_dry_run):
        raise AssertionError(
            "protected checkout Git behavior mismatched: "
            + repr((ignored_skill, protected_staged_paths,
                    protected_clean_dry_run, force_clean_dry_run))
        )

    escaped_path_rejected = False
    try:
        store.read_file(SKILL_ID, revision["revision_id"], "../SKILL.md")
    except SkillStoreError:
        escaped_path_rejected = True
    unsafe_id_rejected = False
    try:
        runner._materialize(root / "invalid-target", {
            "skill_id": "../escape", "revision_id": revision["revision_id"],
            "tree_hash": revision["tree_hash"],
        })
    except (RunnerError, SkillStoreError):
        unsafe_id_rejected = True

    (materialized / "SKILL.md").write_bytes(skill_bytes + b"edited\n")
    post_edit_skill_hash = tree_hash(inventory(materialized))
    post_run_workspace_hash = content_hash(effective_workspace)
    source_hash_after_edit = tree_hash(inventory(skill_source))
    stored_hash_after_edit = store.revision(SKILL_ID, revision["revision_id"])["tree_hash"]
    clean_after_edit = git("status", "--porcelain", cwd=effective_workspace)
    if (post_edit_skill_hash == source_tree_hash or
            post_run_workspace_hash == effective_workspace_hash or
            source_hash_after_edit != source_tree_hash or
            stored_hash_after_edit != source_tree_hash):
        raise AssertionError("edit isolation or hash-change check failed")
    if any((clean_before, clean_effective_before, clean_after_materialization,
            clean_after_edit)):
        raise AssertionError("source or effective checkout became dirty")
    if not escaped_path_rejected or not unsafe_id_rejected:
        raise AssertionError("path escape was not rejected")
    if offered["use_evidence"] != "offered":
        raise AssertionError("synthetic path claimed native skill use")

    tampered_store = SkillStore(root / "tampered-store")
    tampered_revision = tampered_store.import_skill(SKILL_ID, skill_source)
    tampered_bundle = (tampered_store._revision_dir(
        SKILL_ID, tampered_revision["revision_id"]) / "bundle" / "SKILL.md")
    tampered_bundle.write_bytes(skill_bytes + b"tampered\n")
    tampered_runner = LocalRunner(root / "tampered-state", tampered_store.root,
                                  workspace, check_docker=False, max_model_turns=0)
    refused_tampered_revision = False
    tampered_target = root / "tampered-effective"
    tampered_target.mkdir()
    try:
        tampered_runner._materialize(tampered_target, {
            "skill_id": SKILL_ID,
            "revision_id": tampered_revision["revision_id"],
            "tree_hash": tampered_revision["tree_hash"],
        })
    except SkillStoreError:
        refused_tampered_revision = True
    if (not refused_tampered_revision or
            (tampered_target / ".agents" / "skills" / SKILL_ID).exists()):
        raise AssertionError("tampered revision reached the effective workspace")

    shutil.rmtree(effective_workspace / ".agents")
    clean_after_cleanup = git("status", "--porcelain", cwd=effective_workspace)
    if clean_after_cleanup:
        raise AssertionError("cleanup dirtied source repository")
    return {
        "line_ending": "CRLF" if line_ending == b"\r\n" else "LF",
        "source_file_sha256": digest(skill_bytes),
        "source_tree_hash": source_tree_hash,
        "effective_skill_hash": effective_skill_hash,
        "post_edit_skill_hash": post_edit_skill_hash,
        "source_workspace_hash": source_workspace_hash,
        "checkout_before_skill_hash": checkout_before_skill_hash,
        "effective_workspace_hash": effective_workspace_hash,
        "post_run_workspace_hash": post_run_workspace_hash,
        "source_hash_after_edit": source_hash_after_edit,
        "stored_hash_after_edit": stored_hash_after_edit,
        "path_escape_rejected": escaped_path_rejected,
        "unsafe_id_rejected": unsafe_id_rejected,
        "tampered_revision_refused_before_materialization": refused_tampered_revision,
        "git_status_before": clean_before,
        "git_status_effective_before": clean_effective_before,
        "git_status_after_materialization": clean_after_materialization,
        "git_status_after_edit": clean_after_edit,
        "git_status_after_cleanup": clean_after_cleanup,
        "unprotected_status": risk_status,
        "unprotected_add_all_paths": risk_staged_paths,
        "unprotected_clean_dry_run": risk_clean_dry_run,
        "unprotected_staged_skill_sha256": digest(staged_skill),
        "git_checkout_converted_lf_to_crlf": checked_out_bytes.endswith(b"\r\n"),
        "ignored_skill_rule": ignored_skill,
        "protected_add_all_paths": protected_staged_paths,
        "protected_clean_dry_run": protected_clean_dry_run,
        "force_clean_dry_run": force_clean_dry_run,
        "discovery_path": ".agents/skills/" + SKILL_ID + "/SKILL.md",
        "native_discovery": "unverified; no model call",
        "use_evidence": offered["use_evidence"],
    }


def main(output_path=None):
    with TemporaryDirectory(prefix="laomedo-exp08-") as temp:
        root = Path(temp)
        observations = {
            "lf": run_case(b"\n", root / "lf"),
            "crlf": run_case(b"\r\n", root / "crlf"),
        }
    if output_path is not None:
        output = Path(output_path)
        with output.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(observations, indent=2) + "\n")
        print(output)
    return observations


if __name__ == "__main__":
    if sys.argv[1:] == ["--record"]:
        main(Path(__file__).with_name("observation.json"))
    elif len(sys.argv) == 1:
        main()
        print("EXP-08: LF and CRLF Git checkout cases passed")
    else:
        raise SystemExit("usage: python -m experiments.exp08.probe [--record]")
