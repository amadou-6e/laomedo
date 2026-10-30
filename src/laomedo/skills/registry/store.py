"""Immutable skill revisions and reviewable drafts for a local prototype.

This module validates filesystem trees after writes. It is not an OS sandbox
for an untrusted editing process; the runner must enforce that boundary."""

from __future__ import annotations

from laomedo.skills.registry.files import inventory
from laomedo.skills.registry.files import is_link
from laomedo.skills.registry.files import read_json
from laomedo.skills.registry.files import write_json
from laomedo.skills.registry.hashing import file_hashes
from laomedo.skills.registry.hashing import hash_bytes
from laomedo.skills.registry.hashing import tree_hash
from laomedo.skills.registry.paths import validate_name
from laomedo.skills.registry.paths import validate_relative_path
from laomedo.skills.registry.policy import validate_draft
from laomedo.skills.registry.policy import validate_policy

from pathlib import Path
from pathlib import PurePosixPath
from uuid import uuid4
from laomedo.skills.registry.settings import HASH
from laomedo.skills.registry.errors import ConflictError
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.models import (
    FrozenSkillDraft,
    SkillDraft,
    SkillPolicyReference,
    SkillRevision,
)
import os
import shutil


class SkillStore:
    def __init__(self, root: Path, draft_root: Path | None = None):
        self.root = root.resolve()
        draft_root = draft_root or (self.root.parent / (self.root.name + "-drafts"))
        self.draft_root = draft_root.resolve()
        if is_link(root):
            raise SkillStoreError("linked_store_root")
        if is_link(draft_root):
            raise SkillStoreError("linked_draft_root")
        if (
            self.root == self.draft_root
            or self.root.is_relative_to(self.draft_root)
            or self.draft_root.is_relative_to(self.root)
        ):
            raise SkillStoreError("draft_root_overlaps_store")
        if any(
            (candidate / ".git").exists()
            for checked in (self.root, self.draft_root)
            for candidate in (checked, *checked.parents)
        ):
            raise SkillStoreError("store_inside_git_tree")
        self.root.mkdir(parents=True, exist_ok=True)
        self.draft_root.mkdir(parents=True, exist_ok=True)

    def _skill(self, skill_id: str) -> Path:
        return self.root / "skills" / validate_name(skill_id)

    def _draft(self, draft_id: str) -> Path:
        try:
            from uuid import UUID

            canonical = str(UUID(draft_id))
        except (ValueError, AttributeError, TypeError):
            raise SkillStoreError("invalid_draft_id") from None
        if canonical != draft_id:
            raise SkillStoreError("invalid_draft_id")
        return self.root / "drafts" / draft_id

    def _workspace(self, draft_id: str) -> Path:
        self._draft(draft_id)
        return self.draft_root / draft_id

    def _revision_dir(self, skill_id: str, revision_id: str) -> Path:
        if not HASH.fullmatch(revision_id):
            raise SkillStoreError("invalid_revision_id")
        return self._skill(skill_id) / "revisions" / revision_id[7:]

    def _store_revision(
        self,
        skill_id: str,
        source: Path,
        parent_revision: str | None,
        draft_id: str | None = None,
    ) -> dict:
        source_files = inventory(source)
        revision_id = tree_hash(source_files)
        target = self._revision_dir(skill_id, revision_id)
        if target.exists():
            existing = self.revision(skill_id, revision_id)
            if existing["tree_hash"] != revision_id:
                raise SkillStoreError("revision_hash_mismatch")
            return existing
        target.parent.mkdir(parents=True, exist_ok=True)
        staging = target.parent / (".pending-" + uuid4().hex)
        staging.mkdir()
        try:
            shutil.copytree(source, staging / "bundle")
            copied_files = inventory(staging / "bundle")
            if tree_hash(copied_files) != revision_id:
                raise SkillStoreError("source_changed_while_copying")
            revision = SkillRevision(
                skill_id=skill_id,
                revision_id=revision_id,
                tree_hash=revision_id,
                file_hashes=file_hashes(copied_files),
                parent_revision=parent_revision,
                draft_id=draft_id,
            )
            record = revision.to_record()
            write_json(staging / "record.json", record)
            staging.rename(target)
            return record
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def import_skill(self, skill_id: str, source: Path) -> dict:
        """Import an initial immutable revision; never replace an existing latest."""
        validate_name(skill_id)
        resolved_source = source.resolve()
        if (
            self.root == resolved_source
            or self.root.is_relative_to(resolved_source)
            or resolved_source.is_relative_to(self.root)
        ):
            raise SkillStoreError("source_overlaps_store")
        skill = self._skill(skill_id)
        skill.mkdir(parents=True, exist_ok=True)
        lock = skill / "import.lock"
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ConflictError("import_busy") from None
        try:
            os.close(descriptor)
            if (skill / "latest.json").exists():
                raise ConflictError("skill_already_exists")
            record = self._store_revision(skill_id, source, None)
            write_json(
                skill / "latest.json",
                {
                    "revision_id": record["revision_id"],
                    "tree_hash": record["tree_hash"],
                },
            )
            return record
        finally:
            lock.unlink(missing_ok=True)

    def revision(self, skill_id: str, revision_id: str | None = None) -> dict:
        if revision_id is None:
            pointer = read_json(self._skill(skill_id) / "latest.json")
            revision_id = pointer["revision_id"]
            if pointer.get("tree_hash") != revision_id:
                raise SkillStoreError("latest_pointer_integrity_failure")
        folder = self._revision_dir(skill_id, revision_id)
        record = read_json(folder / "record.json")
        files = inventory(folder / "bundle")
        if (
            record.get("skill_id") != skill_id
            or record.get("revision_id") != revision_id
            or tree_hash(files) != revision_id
            or record.get("file_hashes") != file_hashes(files)
        ):
            raise SkillStoreError("revision_integrity_failure")
        return record

    def read_file(self, skill_id: str, revision_id: str, relative: str) -> dict:
        relative = validate_relative_path(relative)
        record = self.revision(skill_id, revision_id)
        if relative not in record["file_hashes"]:
            raise SkillStoreError("file_not_in_revision")
        data = (
            self._revision_dir(skill_id, revision_id)
            / "bundle"
            / PurePosixPath(relative)
        ).read_bytes()
        if hash_bytes(data) != record["file_hashes"][relative]:
            raise SkillStoreError("revision_integrity_failure")
        return {
            "content": data,
            "file_hash": record["file_hashes"][relative],
            "revision_id": revision_id,
            "relative_path": relative,
        }

    def create_draft(self, skill_id: str, base_revision: str, policy: dict) -> dict:
        base = self.revision(skill_id, base_revision)
        policy_reference = validate_policy(policy)
        draft_id = str(uuid4())
        folder = self._draft(draft_id)
        folder.mkdir(parents=True)
        try:
            shutil.copytree(
                self._revision_dir(skill_id, base_revision) / "bundle",
                self._workspace(draft_id),
            )
            if tree_hash(inventory(self._workspace(draft_id))) != base_revision:
                raise SkillStoreError("draft_copy_mismatch")
            write_json(folder / "policy.json", policy)
            draft = SkillDraft(
                draft_id=draft_id,
                skill_id=skill_id,
                base_revision=base_revision,
                base_tree_hash=base["tree_hash"],
                policy_ref=SkillPolicyReference(**policy_reference),
            )
            write_json(folder / "record.json", draft.to_record())
            return draft.to_record()
        except Exception:
            shutil.rmtree(folder)
            workspace = self._workspace(draft_id)
            if workspace.exists():
                shutil.rmtree(workspace)
            raise

    def draft_workspace(self, draft_id: str) -> Path:
        folder = self._draft(draft_id)
        record = read_json(folder / "record.json")
        if record.get("status") != "open":
            raise SkillStoreError("draft_not_open")
        return self._workspace(draft_id)

    def freeze_draft(
        self, draft_id: str, *, editor_kind="human", edit_run_id=None, trace_ref=None
    ) -> dict:
        """Create a review artifact. This never promotes it."""
        if editor_kind not in {"human", "operator", "agent"} or (
            editor_kind == "agent"
            and (not isinstance(edit_run_id, str) or not edit_run_id)
        ):
            raise SkillStoreError("invalid_editor_provenance")
        folder = self._draft(draft_id)
        record = read_json(folder / "record.json")
        if record.get("status") != "open":
            raise SkillStoreError("draft_not_open")
        policy = read_json(folder / "policy.json")
        if validate_policy(policy) != record["policy_ref"]:
            raise SkillStoreError("policy_integrity_failure")
        base_record = self.revision(record["skill_id"], record["base_revision"])
        base = inventory(
            self._revision_dir(record["skill_id"], record["base_revision"]) / "bundle"
        )
        if base_record["tree_hash"] != record["base_tree_hash"]:
            raise SkillStoreError("base_integrity_failure")
        workspace = self._workspace(draft_id)
        try:
            proposed = inventory(workspace)
            errors = validate_draft(base, proposed, policy)
        except SkillStoreError as exc:
            proposed = None
            errors = [str(exc)]
        if proposed is not None and tree_hash(proposed) == record["base_tree_hash"]:
            errors.append("no_change")
        frozen = folder / "frozen"
        if proposed is not None and not errors:
            if not frozen.exists():
                shutil.copytree(workspace, frozen)
            if tree_hash(inventory(frozen)) != tree_hash(proposed):
                raise ConflictError("interrupted_freeze_conflict")
        result = FrozenSkillDraft.from_review(
            record,
            base,
            proposed,
            errors,
            draft_id=draft_id,
            editor_kind=editor_kind,
            edit_run_id=edit_run_id,
            trace_ref=trace_ref,
        ).to_record()
        write_json(folder / "result.json", result)
        record["status"] = "frozen"
        write_json(folder / "record.json", record)
        return result

    def promote_draft(
        self,
        draft_id: str,
        *,
        expected_base_revision: str,
        reviewed_draft_hash: str,
        expected_policy_hash: str,
    ) -> dict:
        """Separate reviewed operation with a compare-and-swap latest update."""
        folder = self._draft(draft_id)
        record = read_json(folder / "record.json")
        result = read_json(folder / "result.json")
        if record.get("status") != "frozen" or not result.get("promotion_eligible"):
            raise SkillStoreError("draft_not_eligible")
        policy = read_json(folder / "policy.json")
        if validate_policy(policy) != record.get("policy_ref"):
            raise SkillStoreError("policy_integrity_failure")
        if (
            expected_base_revision != record["base_revision"]
            or reviewed_draft_hash != result["proposed_tree_hash"]
            or expected_policy_hash != record["policy_ref"]["hash"]
            or expected_policy_hash != result["policy_ref"]["hash"]
        ):
            raise ConflictError("reviewed_ref_mismatch")
        frozen = folder / "frozen"
        frozen_files = inventory(frozen)
        if tree_hash(frozen_files) != reviewed_draft_hash:
            raise SkillStoreError("frozen_draft_integrity_failure")
        base_files = inventory(
            self._revision_dir(record["skill_id"], record["base_revision"]) / "bundle"
        )
        if validate_draft(base_files, frozen_files, policy):
            raise SkillStoreError("frozen_draft_validation_failure")
        skill = self._skill(record["skill_id"])
        lock = skill / "promotion.lock"
        try:
            descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise ConflictError("promotion_busy") from None
        try:
            os.close(descriptor)
            current = read_json(skill / "latest.json")
            if (
                current.get("revision_id") == reviewed_draft_hash
                and current.get("draft_id") == draft_id
                and current.get("parent_revision") == expected_base_revision
                and current.get("policy_hash") == expected_policy_hash
            ):
                promoted = self.revision(record["skill_id"], reviewed_draft_hash)
                self._finish_promotion(
                    skill,
                    folder,
                    record,
                    result,
                    expected_base_revision,
                    reviewed_draft_hash,
                )
                return promoted
            if (
                current["revision_id"] != expected_base_revision
                or current["tree_hash"] != record["base_tree_hash"]
            ):
                raise ConflictError("base_revision_changed")
            self.revision(record["skill_id"], expected_base_revision)
            promoted = self._store_revision(
                record["skill_id"], frozen, expected_base_revision, draft_id
            )
            if promoted["tree_hash"] != reviewed_draft_hash:
                raise SkillStoreError("promoted_hash_mismatch")
            write_json(
                skill / "latest.json",
                {
                    "revision_id": promoted["revision_id"],
                    "tree_hash": promoted["tree_hash"],
                    "parent_revision": expected_base_revision,
                    "draft_id": draft_id,
                    "policy_hash": expected_policy_hash,
                },
            )
            self._finish_promotion(
                skill,
                folder,
                record,
                result,
                expected_base_revision,
                reviewed_draft_hash,
            )
            return promoted
        finally:
            lock.unlink(missing_ok=True)

    def _finish_promotion(
        self,
        skill: Path,
        folder: Path,
        record: dict,
        result: dict,
        base_revision: str,
        reviewed_hash: str,
    ) -> None:
        log = skill / "promotions" / (record["draft_id"] + ".json")
        entry = {
            "draft_id": record["draft_id"],
            "base_revision": base_revision,
            "promoted_revision": reviewed_hash,
            "policy_ref": record["policy_ref"],
        }
        log.parent.mkdir(exist_ok=True)
        if log.exists():
            if read_json(log) != entry:
                raise SkillStoreError("promotion_log_conflict")
        else:
            write_json(log, entry)
        result["promotion_performed"] = True
        result["promoted_revision"] = reviewed_hash
        write_json(folder / "result.json", result)
