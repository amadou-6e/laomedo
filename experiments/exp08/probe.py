"""Credential-free skill-byte and workspace-cleanliness probe for EXP-08."""

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from laomedo.local_runner import LocalRunner, RunnerError, _hash_tree
from laomedo.skill_store import SkillStore, SkillStoreError, inventory, tree_hash


SKILL_ID = "exp08-sample"


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                          text=True, check=True).stdout.strip()


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
    effective_workspace = root / "effective-workspace"
    shutil.copytree(workspace, effective_workspace)
    source_workspace_hash = _hash_tree(workspace)
    offered = runner._materialize(effective_workspace, {
        "skill_id": SKILL_ID, "revision_id": revision["revision_id"],
        "tree_hash": revision["tree_hash"],
    })
    materialized = effective_workspace / ".agents" / "skills" / SKILL_ID
    effective_inventory = inventory(materialized)
    effective_skill_hash = tree_hash(effective_inventory)
    if effective_inventory != source_inventory or effective_skill_hash != source_tree_hash:
        raise AssertionError("materialized skill bytes differ")
    effective_workspace_hash = _hash_tree(effective_workspace)
    clean_after_materialization = git("status", "--porcelain", cwd=repository)

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
    post_run_workspace_hash = _hash_tree(effective_workspace)
    source_hash_after_edit = tree_hash(inventory(skill_source))
    stored_hash_after_edit = store.revision(SKILL_ID, revision["revision_id"])["tree_hash"]
    clean_after_edit = git("status", "--porcelain", cwd=repository)
    if (post_edit_skill_hash == source_tree_hash or
            post_run_workspace_hash == effective_workspace_hash or
            source_hash_after_edit != source_tree_hash or
            stored_hash_after_edit != source_tree_hash):
        raise AssertionError("edit isolation or hash-change check failed")
    if any((clean_before, clean_after_materialization, clean_after_edit)):
        raise AssertionError("source repository became dirty")
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

    shutil.rmtree(effective_workspace)
    clean_after_cleanup = git("status", "--porcelain", cwd=repository)
    if clean_after_cleanup:
        raise AssertionError("cleanup dirtied source repository")
    return {
        "line_ending": "CRLF" if line_ending == b"\r\n" else "LF",
        "source_file_sha256": digest(skill_bytes),
        "source_tree_hash": source_tree_hash,
        "effective_skill_hash": effective_skill_hash,
        "post_edit_skill_hash": post_edit_skill_hash,
        "source_workspace_hash": source_workspace_hash,
        "effective_workspace_hash": effective_workspace_hash,
        "post_run_workspace_hash": post_run_workspace_hash,
        "source_hash_after_edit": source_hash_after_edit,
        "stored_hash_after_edit": stored_hash_after_edit,
        "path_escape_rejected": escaped_path_rejected,
        "unsafe_id_rejected": unsafe_id_rejected,
        "tampered_revision_refused_before_materialization": refused_tampered_revision,
        "git_status_before": clean_before,
        "git_status_after_materialization": clean_after_materialization,
        "git_status_after_edit": clean_after_edit,
        "git_status_after_cleanup": clean_after_cleanup,
        "discovery_path": ".agents/skills/" + SKILL_ID + "/SKILL.md",
        "native_discovery": "unverified; no model call",
        "use_evidence": offered["use_evidence"],
    }


def main():
    with TemporaryDirectory(prefix="laomedo-exp08-") as temp:
        root = Path(temp)
        observations = {
            "lf": run_case(b"\n", root / "lf"),
            "crlf": run_case(b"\r\n", root / "crlf"),
        }
    output = Path(__file__).with_name("observation.json")
    output.write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
