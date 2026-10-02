"""Validated manifest references; no host paths or credential/profile imports."""
import hashlib
from pathlib import PurePosixPath
import re
from uuid import UUID


class ArtifactError(ValueError):
    pass


HASH = re.compile(r"sha256:[0-9a-f]{64}")


def relative_path(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value or
            "\x00" in value or value.startswith("/") or
            any(p in {"", ".", ".."} for p in value.split("/"))):
        raise ArtifactError("unsafe_artifact_path")
    parts = PurePosixPath(value).parts
    if any(p.startswith(".") or p.casefold() in {
            "auth.json", "credentials", "credentials.json", "token", "tokens.json",
            "id_rsa", "id_ed25519", "sessions", "session.json", "raw-events.jsonl"}
           or p.casefold().endswith((".pem", ".key", ".p12")) for p in parts):
        raise ArtifactError("protected_artifact_path")
    return value


def selections(items):
    if not isinstance(items, list) or len(items) > 32:
        raise ArtifactError("invalid_artifact_selection")
    result, destinations = [], set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {
                "provider", "run_id", "snapshot_hash", "path", "content_hash", "destination"}:
            raise ArtifactError("invalid_artifact_reference")
        if item["provider"] not in {"codex", "opencode"}:
            raise ArtifactError("invalid_artifact_provider")
        try:
            if str(UUID(item["run_id"])) != item["run_id"]:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ArtifactError("invalid_artifact_run") from None
        for field in ("snapshot_hash", "content_hash"):
            if not isinstance(item[field], str) or not HASH.fullmatch(item[field]):
                raise ArtifactError("invalid_artifact_hash")
        relative_path(item["path"])
        destination = relative_path(item["destination"])
        if not destination.startswith("handoff/"):
            raise ArtifactError("artifact_destination_must_be_handoff")
        folded = destination.casefold()
        if folded in destinations or any(folded.startswith(d + "/") or d.startswith(folded + "/")
                                         for d in destinations):
            raise ArtifactError("artifact_destination_conflict")
        destinations.add(folded)
        result.append(dict(item))
    return result


def import_selected(items, workspace, resolve, hash_tree):
    """Resolve only runner-owned snapshots, verify each source, copy selected bytes."""
    selected = selections(items)
    staged, total = [], 0
    roots = {}
    for ref in selected:
        snapshot, record = resolve(ref["provider"], ref["run_id"])
        if (record.get("status") != "completed" or record.get("post_run_hash") != ref["snapshot_hash"] or
                hash_tree(snapshot) != ref["snapshot_hash"]):
            raise ArtifactError("artifact_snapshot_mismatch")
        source = snapshot / ref["path"]
        # hash_tree rejects every link/reparse/hard-link/special entry in source tree.
        if not source.is_file() or source.stat().st_size > 1024 * 1024:
            raise ArtifactError("artifact_file_missing_or_too_large")
        data = source.read_bytes()
        total += len(data)
        if total > 8 * 1024 * 1024:
            raise ArtifactError("artifact_total_too_large")
        if "sha256:" + hashlib.sha256(data).hexdigest() != ref["content_hash"]:
            raise ArtifactError("artifact_content_mismatch")
        target = workspace / ref["destination"]
        if target.exists() or any(p.exists() and not p.is_dir()
                                  for p in target.parents if p != workspace and p.is_relative_to(workspace)):
            raise ArtifactError("artifact_destination_conflict")
        staged.append((target, data))
        roots[snapshot] = ref["snapshot_hash"]
    for target, data in staged:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for snapshot, expected in roots.items():
        if hash_tree(snapshot) != expected:
            raise ArtifactError("artifact_source_changed_during_import")
    return selected
