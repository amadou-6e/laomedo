"""Immutable skill revisions and reviewable drafts for a local prototype.

This module validates filesystem trees after writes. It is not an OS sandbox
for an untrusted editing process; the runner must enforce that boundary.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from uuid import uuid4


NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


class SkillStoreError(ValueError):
    pass


class ConflictError(SkillStoreError):
    pass


def _hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _safe_name(value: str) -> str:
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise SkillStoreError("invalid_skill_id")
    return value


def _safe_relative(value: str) -> str:
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise SkillStoreError("unsafe_relative_path")
    path = PurePosixPath(value)
    if (not value or value.startswith("/") or ":" in value or
            any(part in (".", "..") for part in value.split("/")) or
            path.as_posix() != value):
        raise SkillStoreError("unsafe_relative_path")
    return value


def _is_link(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return (stat.S_ISLNK(metadata.st_mode) or
            bool(getattr(metadata, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def inventory(root: Path) -> dict[str, bytes]:
    """Read regular files only; reject links, junctions, and special files."""
    if _is_link(root) or not root.is_dir():
        raise SkillStoreError("invalid_tree_root")
    files = {}
    folders = []
    for parent, directories, names in os.walk(root, followlinks=False):
        for name in sorted(directories + names):
            path = Path(parent) / name
            if _is_link(path):
                raise SkillStoreError("linked_path")
            if path.is_dir():
                folders.append(path.relative_to(root).as_posix())
                continue
            if not path.is_file():
                raise SkillStoreError("special_file")
            if path.stat().st_nlink > 1:
                raise SkillStoreError("hardlinked_file")
            relative = path.relative_to(root).as_posix()
            _safe_relative(relative)
            files[relative] = path.read_bytes()
    if "SKILL.md" not in files:
        raise SkillStoreError("missing_skill_file")
    if any(not any(name.startswith(folder + "/") for name in files)
           for folder in folders):
        raise SkillStoreError("empty_directory")
    return files


def tree_hash(files: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for relative, data in sorted(files.items()):
        encoded = _safe_relative(relative).encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return "sha256:" + digest.hexdigest()


def file_hashes(files: dict[str, bytes]) -> dict[str, str]:
    return {path: _hash(data) for path, data in sorted(files.items())}


def validate_policy(policy: dict) -> dict:
    required = ("policy_id", "revision_id", "allowed_paths", "allowed_suffixes",
                "allow_new_files", "allow_deletions", "allow_scripts", "allow_dependencies",
                "allow_assets", "required_frontmatter",
                "permitted_validation_commands", "max_files", "max_file_bytes")
    if not isinstance(policy, dict) or any(key not in policy for key in required):
        raise SkillStoreError("invalid_policy")
    _safe_name(policy["policy_id"])
    if not isinstance(policy["revision_id"], str) or not policy["revision_id"]:
        raise SkillStoreError("invalid_policy_revision")
    paths = policy["allowed_paths"]
    if (not isinstance(paths, list) or not paths or
            any(not isinstance(path, str) for path in paths)):
        raise SkillStoreError("invalid_allowed_paths")
    for path in paths:
        _safe_relative(path)
    if len(paths) != len(set(paths)) or "SKILL.md" not in paths:
        raise SkillStoreError("invalid_allowed_paths")
    suffixes = policy["allowed_suffixes"]
    if (not isinstance(suffixes, list) or not suffixes or
            any(not isinstance(item, str) or not item.startswith(".")
                for item in suffixes)):
        raise SkillStoreError("invalid_suffixes")
    for key in ("allow_new_files", "allow_deletions", "allow_scripts", "allow_dependencies",
                "allow_assets"):
        if not isinstance(policy[key], bool):
            raise SkillStoreError("invalid_policy_boolean")
    safe_documents = {".md", ".txt", ".json", ".yaml", ".yml"}
    safe_assets = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf"}
    script_suffixes = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx",
                       ".sh", ".ps1", ".bat", ".cmd", ".rb", ".pl", ".php"}
    if not policy["allow_scripts"] and any(
            "scripts" in PurePosixPath(path).parts or
            PurePosixPath(path).suffix.lower() not in
            (safe_documents | (safe_assets if policy["allow_assets"] else set()))
            for path in paths):
        raise SkillStoreError("policy_grants_disallowed_scripts")
    if not policy["allow_dependencies"] and any(
            PurePosixPath(path).name in ("requirements.txt", "package.json",
                                           "pyproject.toml", "Pipfile")
            for path in paths):
        raise SkillStoreError("policy_grants_disallowed_dependencies")
    if not policy["allow_assets"] and any(
            PurePosixPath(path).suffix.lower() not in
            (safe_documents | (script_suffixes if policy["allow_scripts"] else set()))
            for path in paths):
        raise SkillStoreError("policy_grants_disallowed_assets")
    for key in ("required_frontmatter", "permitted_validation_commands"):
        if not isinstance(policy[key], list) or not all(
                isinstance(item, str) for item in policy[key]):
            raise SkillStoreError("invalid_policy_list")
    for key in ("max_files", "max_file_bytes"):
        if not isinstance(policy[key], int) or isinstance(policy[key], bool) or policy[key] <= 0:
            raise SkillStoreError("invalid_policy_limit")
    return {"policy_id": policy["policy_id"],
            "revision_id": policy["revision_id"],
            "hash": _hash(_canonical_json(policy))}


def validate_draft(base: dict[str, bytes], draft: dict[str, bytes],
                   policy: dict) -> list[str]:
    validate_policy(policy)
    errors = []
    if len(draft) > policy["max_files"]:
        errors.append("too_many_files")
    changed = {key for key in base.keys() | draft.keys()
               if base.get(key) != draft.get(key)}
    for relative in changed:
        if (relative not in policy["allowed_paths"] or
                PurePosixPath(relative).suffix not in policy["allowed_suffixes"]):
            errors.append("forbidden_path")
        if relative not in base and not policy["allow_new_files"]:
            errors.append("new_file_forbidden")
        if relative not in draft and not policy["allow_deletions"]:
            errors.append("deletion_forbidden")
        if relative in draft:
            try:
                draft[relative].decode("utf-8")
            except UnicodeDecodeError:
                errors.append("non_utf8_changed_file")
    for relative, data in draft.items():
        if len(data) > policy["max_file_bytes"]:
            errors.append("file_too_large")
        if relative != "SKILL.md":
            continue
        try:
            content = data.decode("utf-8").replace("\r\n", "\n")
        except UnicodeDecodeError:
            errors.append("skill_not_utf8")
            continue
        if not content.startswith("---\n") or "\n---\n" not in content[4:]:
            errors.append("frontmatter_missing")
            continue
        frontmatter = content.split("\n---\n", 1)[0]
        for field in policy["required_frontmatter"]:
            if not any(line.startswith(field + ": ") and
                       line.split(":", 1)[1].strip()
                       for line in frontmatter.splitlines()):
                errors.append("frontmatter_field_missing")
    return sorted(set(errors))


def patch_for(base: dict[str, bytes], draft: dict[str, bytes]) -> str:
    chunks = []
    for relative in sorted(base.keys() | draft.keys()):
        if base.get(relative) == draft.get(relative):
            continue
        try:
            before = base.get(relative, b"").decode("utf-8")
            after = draft.get(relative, b"").decode("utf-8")
        except UnicodeDecodeError:
            chunks.append(f"--- base/{relative}\n+++ draft/{relative}\n")
            chunks.append(f"-bytes {base.get(relative, b'')!r}\n")
            chunks.append(f"+bytes {draft.get(relative, b'')!r}\n")
            continue
        def exact_lines(value: str) -> list[str]:
            return [line.encode("unicode_escape").decode("ascii") + "\n"
                    for line in value.splitlines(keepends=True)]
        chunks.extend(difflib.unified_diff(
            exact_lines(before), exact_lines(after),
            fromfile="base/" + relative, tofile="draft/" + relative))
    return "".join(chunks)


def _write_json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    pending.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    os.replace(pending, path)


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SkillStoreError("invalid_record")
    return value


class SkillStore:
    def __init__(self, root: Path, draft_root: Path | None = None):
        self.root = root.resolve()
        draft_root = draft_root or (self.root.parent / (self.root.name + "-drafts"))
        self.draft_root = draft_root.resolve()
        if _is_link(root):
            raise SkillStoreError("linked_store_root")
        if _is_link(draft_root):
            raise SkillStoreError("linked_draft_root")
        if (self.root == self.draft_root or
                self.root.is_relative_to(self.draft_root) or
                self.draft_root.is_relative_to(self.root)):
            raise SkillStoreError("draft_root_overlaps_store")
        if any((candidate / ".git").exists() for checked in
               (self.root, self.draft_root) for candidate in
               (checked, *checked.parents)):
            raise SkillStoreError("store_inside_git_tree")
        self.root.mkdir(parents=True, exist_ok=True)
        self.draft_root.mkdir(parents=True, exist_ok=True)

    def _skill(self, skill_id: str) -> Path:
        return self.root / "skills" / _safe_name(skill_id)

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

    def _store_revision(self, skill_id: str, source: Path,
                        parent_revision: str | None, draft_id: str | None = None) -> dict:
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
            record = {"skill_id": skill_id, "revision_id": revision_id,
                      "tree_hash": revision_id, "file_hashes": file_hashes(copied_files),
                      "parent_revision": parent_revision, "draft_id": draft_id}
            _write_json(staging / "record.json", record)
            staging.rename(target)
            return record
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def import_skill(self, skill_id: str, source: Path) -> dict:
        """Import an initial immutable revision; never replace an existing latest."""
        _safe_name(skill_id)
        resolved_source = source.resolve()
        if (self.root == resolved_source or
                self.root.is_relative_to(resolved_source) or
                resolved_source.is_relative_to(self.root)):
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
            _write_json(skill / "latest.json", {"revision_id": record["revision_id"],
                                                 "tree_hash": record["tree_hash"]})
            return record
        finally:
            lock.unlink(missing_ok=True)

    def revision(self, skill_id: str, revision_id: str | None = None) -> dict:
        if revision_id is None:
            pointer = _read_json(self._skill(skill_id) / "latest.json")
            revision_id = pointer["revision_id"]
            if pointer.get("tree_hash") != revision_id:
                raise SkillStoreError("latest_pointer_integrity_failure")
        folder = self._revision_dir(skill_id, revision_id)
        record = _read_json(folder / "record.json")
        files = inventory(folder / "bundle")
        if (record.get("skill_id") != skill_id or record.get("revision_id") != revision_id
                or tree_hash(files) != revision_id
                or record.get("file_hashes") != file_hashes(files)):
            raise SkillStoreError("revision_integrity_failure")
        return record

    def read_file(self, skill_id: str, revision_id: str,
                  relative: str) -> dict:
        relative = _safe_relative(relative)
        record = self.revision(skill_id, revision_id)
        if relative not in record["file_hashes"]:
            raise SkillStoreError("file_not_in_revision")
        data = (self._revision_dir(skill_id, revision_id) / "bundle" /
                PurePosixPath(relative)).read_bytes()
        if _hash(data) != record["file_hashes"][relative]:
            raise SkillStoreError("revision_integrity_failure")
        return {"content": data, "file_hash": record["file_hashes"][relative],
                "revision_id": revision_id, "relative_path": relative}

    def create_draft(self, skill_id: str, base_revision: str,
                     policy: dict) -> dict:
        base = self.revision(skill_id, base_revision)
        policy_reference = validate_policy(policy)
        draft_id = str(uuid4())
        folder = self._draft(draft_id)
        folder.mkdir(parents=True)
        try:
            shutil.copytree(self._revision_dir(skill_id, base_revision) / "bundle",
                            self._workspace(draft_id))
            if tree_hash(inventory(self._workspace(draft_id))) != base_revision:
                raise SkillStoreError("draft_copy_mismatch")
            _write_json(folder / "policy.json", policy)
            record = {"draft_id": draft_id, "skill_id": skill_id,
                      "base_revision": base_revision, "base_tree_hash": base["tree_hash"],
                      "policy_ref": policy_reference, "status": "open"}
            _write_json(folder / "record.json", record)
            return record
        except Exception:
            shutil.rmtree(folder)
            workspace = self._workspace(draft_id)
            if workspace.exists():
                shutil.rmtree(workspace)
            raise

    def draft_workspace(self, draft_id: str) -> Path:
        folder = self._draft(draft_id)
        record = _read_json(folder / "record.json")
        if record.get("status") != "open":
            raise SkillStoreError("draft_not_open")
        return self._workspace(draft_id)

    def freeze_draft(self, draft_id: str) -> dict:
        """Create a review artifact. This never promotes it."""
        folder = self._draft(draft_id)
        record = _read_json(folder / "record.json")
        if record.get("status") != "open":
            raise SkillStoreError("draft_not_open")
        policy = _read_json(folder / "policy.json")
        if validate_policy(policy) != record["policy_ref"]:
            raise SkillStoreError("policy_integrity_failure")
        base_record = self.revision(record["skill_id"], record["base_revision"])
        base = inventory(self._revision_dir(record["skill_id"],
                                            record["base_revision"]) / "bundle")
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
        eligible = proposed is not None and not errors
        observed_hash = tree_hash(proposed) if proposed is not None else None
        result = {"draft_id": draft_id, "base_ref": {
            "revision_id": record["base_revision"],
            "tree_hash": record["base_tree_hash"]},
            "policy_ref": record["policy_ref"],
            "editor_kind": "human", "edit_run_id": None, "trace_ref": None,
            "observed_tree_hash": observed_hash,
            "proposed_tree_hash": observed_hash if eligible else None,
            "proposed_ref": ({"tree_hash": observed_hash,
                              "file_hashes": file_hashes(proposed)}
                             if eligible else None),
            "changed_paths": (sorted(path for path in base.keys() | proposed.keys()
                                     if base.get(path) != proposed.get(path))
                              if proposed is not None else []),
            "patch": patch_for(base, proposed) if proposed is not None else None,
            "validation_errors": sorted(set(errors)),
            "validation_results": [{"validator": "structural-v1",
                                    "passed": not errors,
                                    "errors": sorted(set(errors))}],
            "evaluation_results": [],
            "promotion_eligible": eligible,
            "promotion_performed": False}
        _write_json(folder / "result.json", result)
        record["status"] = "frozen"
        _write_json(folder / "record.json", record)
        return result

    def promote_draft(self, draft_id: str, *, expected_base_revision: str,
                      reviewed_draft_hash: str,
                      expected_policy_hash: str) -> dict:
        """Separate reviewed operation with a compare-and-swap latest update."""
        folder = self._draft(draft_id)
        record = _read_json(folder / "record.json")
        result = _read_json(folder / "result.json")
        if record.get("status") != "frozen" or not result.get("promotion_eligible"):
            raise SkillStoreError("draft_not_eligible")
        policy = _read_json(folder / "policy.json")
        if validate_policy(policy) != record.get("policy_ref"):
            raise SkillStoreError("policy_integrity_failure")
        if (expected_base_revision != record["base_revision"] or
                reviewed_draft_hash != result["proposed_tree_hash"] or
                expected_policy_hash != record["policy_ref"]["hash"] or
                expected_policy_hash != result["policy_ref"]["hash"]):
            raise ConflictError("reviewed_ref_mismatch")
        frozen = folder / "frozen"
        frozen_files = inventory(frozen)
        if tree_hash(frozen_files) != reviewed_draft_hash:
            raise SkillStoreError("frozen_draft_integrity_failure")
        base_files = inventory(self._revision_dir(
            record["skill_id"], record["base_revision"]) / "bundle")
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
            current = _read_json(skill / "latest.json")
            if (current.get("revision_id") == reviewed_draft_hash and
                    current.get("draft_id") == draft_id and
                    current.get("parent_revision") == expected_base_revision and
                    current.get("policy_hash") == expected_policy_hash):
                promoted = self.revision(record["skill_id"], reviewed_draft_hash)
                self._finish_promotion(skill, folder, record, result,
                                       expected_base_revision, reviewed_draft_hash)
                return promoted
            if (current["revision_id"] != expected_base_revision or
                    current["tree_hash"] != record["base_tree_hash"]):
                raise ConflictError("base_revision_changed")
            self.revision(record["skill_id"], expected_base_revision)
            promoted = self._store_revision(record["skill_id"], frozen,
                                            expected_base_revision, draft_id)
            if promoted["tree_hash"] != reviewed_draft_hash:
                raise SkillStoreError("promoted_hash_mismatch")
            _write_json(skill / "latest.json", {"revision_id": promoted["revision_id"],
                                                 "tree_hash": promoted["tree_hash"],
                                                 "parent_revision": expected_base_revision,
                                                 "draft_id": draft_id,
                                                 "policy_hash": expected_policy_hash})
            self._finish_promotion(skill, folder, record, result,
                                   expected_base_revision, reviewed_draft_hash)
            return promoted
        finally:
            lock.unlink(missing_ok=True)

    def _finish_promotion(self, skill: Path, folder: Path, record: dict,
                          result: dict, base_revision: str, reviewed_hash: str) -> None:
        log = skill / "promotions" / (record["draft_id"] + ".json")
        entry = {"draft_id": record["draft_id"], "base_revision": base_revision,
                 "promoted_revision": reviewed_hash, "policy_ref": record["policy_ref"]}
        log.parent.mkdir(exist_ok=True)
        if log.exists():
            if _read_json(log) != entry:
                raise SkillStoreError("promotion_log_conflict")
        else:
            _write_json(log, entry)
        result["promotion_performed"] = True
        result["promoted_revision"] = reviewed_hash
        _write_json(folder / "result.json", result)
