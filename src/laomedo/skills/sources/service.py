"""Coordinate source choices and exact registry imports; never launch native processes."""

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit
import json
import os
import re
import tempfile
import threading
import time

from laomedo.skills.inspection.settings import MAX_FILES, MAX_BUNDLE_BYTES
from laomedo.skills.inspection.utils import inspect_skill
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.files import is_link
from laomedo.skills.registry.hashing import tree_hash
from laomedo.skills.registry.models import SkillReference
from laomedo.skills.registry.paths import validate_relative_path
from laomedo.skills.registry.store import SkillStore
from laomedo.skills.sources.bundle import validate_bundle, validate_bundle_path
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.local import LocalSkillSource
from laomedo.skills.sources.models import (
    AdmittedSkillSource,
    SkillSourceChoice,
    PendingSkillImport,
)
from laomedo.skills.sources.repository import GitSkillSource
from laomedo.skills.sources.utils import skill_name


class SkillSources:
    def __init__(self, registry, state, allowed_roots=(), *, repository_provider=None):
        self.store = SkillStore(Path(registry))
        self.state = Path(state).absolute()
        self.state.mkdir(parents=True, exist_ok=True)
        self.local_source = LocalSkillSource(allowed_roots)
        self.repository_source = GitSkillSource(
            self.state, repository_provider=repository_provider
        )
        self.lock = threading.RLock()
        self.index_path = self.state / "index.json"
        self.index = (
            json.loads(self.index_path.read_text(encoding="utf-8"))
            if self.index_path.exists()
            else {}
        )

    def _save(self):
        temp = self.index_path.with_suffix(".pending")
        temp.write_text(json.dumps(self.index, sort_keys=True), encoding="utf-8")
        temp.replace(self.index_path)

    def _source(self, source, *, require_exists=True):
        if not isinstance(source, str) or not source.strip() or len(source) > 2048:
            raise SourceError("source_required")
        source = source.strip()
        parsed = urlsplit(source)
        if parsed.scheme == "https":
            if (
                parsed.hostname not in {"github.com", "gitlab.com"}
                or parsed.username
                or parsed.password
                or parsed.port
                or parsed.query
                or parsed.fragment
                or not re.fullmatch(
                    r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?/?", parsed.path
                )
            ):
                raise SourceError("repository_url_invalid")
            normalized = (
                "https://"
                + parsed.hostname
                + parsed.path.rstrip("/").removesuffix(".git")
                + ".git"
            )
            return AdmittedSkillSource(kind="repository", location=normalized)
        if parsed.scheme == "file":
            if (
                parsed.netloc not in {"", "localhost"}
                or parsed.query
                or parsed.fragment
            ):
                raise SourceError("local_source_invalid")
            value = unquote(parsed.path)
            if os.name == "nt" and re.match(r"^/[A-Za-z]:/", value):
                value = value[1:]
            path = Path(value)
        else:
            path = Path(source)
        if not path.is_absolute():
            raise SourceError("absolute_local_source_required")
        if path.name == "SKILL.md":
            path = path.parent
        if path == self.store.root:
            return AdmittedSkillSource(kind="registry", location=str(path))
        self.local_source.admit(path, require_exists=require_exists)
        return AdmittedSkillSource(kind="local", location=str(path))

    def discover(self, source):
        with self.lock:
            deadline = time.monotonic() + 60
            admitted = self._source(source)
            if admitted.kind == "registry":
                skills = [
                    SkillSourceChoice.for_registry(path.name).to_record()
                    for path in sorted((self.store.root / "skills").iterdir())
                    if path.is_dir() and not is_link(path)
                ]
            elif admitted.kind == "local":
                skills = [
                    item.to_record()
                    for item in self.local_source.discover(
                        Path(admitted.location), deadline
                    )
                ]
            else:
                repository = self.repository_source.repository(
                    admitted.location, refresh=True, deadline=deadline
                )
                discovered = {}
                for revision in repository.refs:
                    entries = self.repository_source.entries(
                        repository.directory, revision.commit, deadline
                    )
                    for path, entry in entries.items():
                        if PurePosixPath(path).name == "SKILL.md":
                            folder = str(PurePosixPath(path).parent)
                            name = skill_name(
                                self.repository_source.read_blob(
                                    repository.directory, entry, deadline
                                ),
                                PurePosixPath(folder).name or "skill",
                            )
                            item = SkillSourceChoice.for_folder(name, folder)
                            discovered[item.choice] = item.to_record()
                            if len(discovered) > 128:
                                raise SourceError("source_limit_exceeded")
                skills = list(discovered.values())
            cached = self.index.setdefault(admitted.location, {})
            known = dict(cached.get("skills", {}))
            known.update({item["choice"]: item for item in skills})
            if len(known) > 128:
                raise SourceError("source_limit_exceeded")
            cached["skills"] = known
            self._save()
            return {
                "kind": admitted.kind,
                "skills": sorted(known.values(), key=lambda item: item["choice"]),
            }

    def _register(self, name, files, origin):
        validate_bundle(files)
        with tempfile.TemporaryDirectory(dir=self.state, prefix="import-") as temp:
            root = Path(temp)
            for relative, content in files.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            # Publish exact bytes without advancing an existing canonical latest pointer.
            skill = self.store._skill(name)
            if (skill / "latest.json").exists():
                record = self.store._store_revision(name, root, None)
            else:
                record = self.store.import_skill(name, root)
        provenance = self.store.root / "source-origins.json"
        origins = (
            json.loads(provenance.read_text(encoding="utf-8"))
            if provenance.exists()
            else {}
        )
        key = name + ":" + record["revision_id"]
        values = origins.setdefault(key, [])
        if origin not in values:
            values.append(origin)
        temporary = provenance.with_suffix(".pending")
        temporary.write_text(json.dumps(origins, sort_keys=True), encoding="utf-8")
        temporary.replace(provenance)
        return SkillReference(
            skill_id=record["skill_id"],
            revision_id=record["revision_id"],
            tree_hash=record["tree_hash"],
        ).to_reference_payload()

    def revisions(self, source, choice):
        with self.lock:
            deadline = time.monotonic() + 60
            admitted = self._source(source)
            cached = self.index.get(admitted.location, {})
            skill = cached.get("skills", {}).get(choice)
            if skill is None:
                raise SourceError("discovered_skill_required")
            if skill["path"] != ".":
                try:
                    validate_relative_path(skill["path"])
                except SkillStoreError:
                    raise SourceError("source_bundle_unsafe") from None
            options = dict(cached.get("revisions", {}).get(choice, {}))
            pending = []

            def offer(files, label, origin):
                validate_bundle(files)
                revision = tree_hash(files)
                reference = SkillReference(
                    skill_id=skill["name"], revision_id=revision, tree_hash=revision
                ).to_reference_payload()
                options[label(revision)] = reference
                pending.append(PendingSkillImport(files=files, origin=origin))

            if admitted.kind == "registry":
                for folder in sorted(
                    (self.store._skill(skill["name"]) / "revisions").iterdir()
                ):
                    reference = SkillReference(
                        skill_id=skill["name"],
                        revision_id="sha256:" + folder.name,
                        tree_hash="sha256:" + folder.name,
                    ).to_reference_payload()
                    inspect_skill(
                        self.store.root, reference["skill_id"], reference["revision_id"]
                    )
                    provenance = self.store.root / "source-origins.json"
                    origins = (
                        json.loads(provenance.read_text(encoding="utf-8"))
                        if provenance.exists()
                        else {}
                    )
                    values = origins.get(
                        skill["name"] + ":" + reference["revision_id"], []
                    )
                    description = (
                        " ; ".join(values) if values else "registry (origin unrecorded)"
                    )
                    options[description + " | " + reference["revision_id"]] = reference
            elif admitted.kind == "local":
                folder = Path(admitted.location) / skill["path"]
                files = self.local_source.read(folder, deadline)
                if files is None:
                    return {
                        "revisions": [
                            {"choice": key, **value}
                            for key, value in sorted(options.items(), reverse=True)
                        ]
                    }
                if skill_name(files["SKILL.md"], folder.name) == skill["name"]:
                    revision = tree_hash(validate_bundle(files))
                    if not any(
                        value["revision_id"] == revision for value in options.values()
                    ):
                        timestamp = datetime.now(timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S UTC"
                        )
                        offer(
                            files,
                            lambda revision: timestamp + " | " + revision,
                            "local: " + admitted.location + " / " + skill["path"],
                        )
            else:
                repository = self.repository_source.repository(
                    admitted.location, deadline=deadline
                )
                prefix = "" if skill["path"] == "." else skill["path"] + "/"
                for revision in repository.refs:
                    label, commit = revision.label, revision.commit
                    entries = self.repository_source.entries(
                        repository.directory, commit, deadline
                    )
                    if prefix + "SKILL.md" not in entries:
                        continue
                    if (
                        skill_name(
                            self.repository_source.read_blob(
                                repository.directory,
                                entries[prefix + "SKILL.md"],
                                deadline,
                            ),
                            PurePosixPath(skill["path"]).name or "skill",
                        )
                        != skill["name"]
                    ):
                        continue
                    files = {}
                    total = 0
                    for path, entry in entries.items():
                        if path.startswith(prefix):
                            validate_bundle_path(path[len(prefix) :])
                            if len(files) >= MAX_FILES:
                                raise SourceError("source_limit_exceeded")
                            content = self.repository_source.read_blob(
                                repository.directory, entry, deadline
                            )
                            total += len(content)
                            if total > MAX_BUNDLE_BYTES:
                                raise SourceError("source_limit_exceeded")
                            files[path[len(prefix) :]] = content
                    offer(
                        files,
                        lambda revision, label=label, commit=commit: label
                        + " @ "
                        + commit
                        + " | "
                        + revision,
                        admitted.location
                        + " / "
                        + skill["path"]
                        + " @ "
                        + label
                        + " "
                        + commit,
                    )
            if len(options) > 64:
                raise SourceError("source_limit_exceeded")
            for candidate in pending:
                self._register(skill["name"], candidate.files, candidate.origin)
            cached.setdefault("revisions", {})[choice] = options
            self._save()
            return {
                "revisions": [
                    {"choice": key, **value}
                    for key, value in sorted(options.items(), reverse=True)
                ]
            }

    def resolve(self, source, choice, revision):
        with self.lock:
            admitted = self._source(source, require_exists=False)
            reference = (
                self.index.get(admitted.location, {})
                .get("revisions", {})
                .get(choice, {})
                .get(revision)
            )
            if reference is None:
                raise SourceError("discovered_revision_required")
            label_hash = revision.rsplit(" | ", 1)[-1]
            if (
                label_hash != reference["revision_id"]
                or reference["tree_hash"] != reference["revision_id"]
            ):
                raise SourceError("source_reference_invalid")
            inspect_skill(
                self.store.root, reference["skill_id"], reference["revision_id"]
            )
            return dict(reference)
