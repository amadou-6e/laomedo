"""Bounded host-side skill discovery. Reading a skill never executes its code."""

from __future__ import annotations

from laomedo.skills.registry.files import is_link
from laomedo.skills.registry.hashing import tree_hash
from laomedo.skills.registry.paths import validate_relative_path

from datetime import datetime
from datetime import timezone
from pathlib import Path
from pathlib import PurePosixPath
from urllib.parse import unquote
from urllib.parse import urlsplit
import hashlib
import json
import laomedo.skills.inspection.settings as _inspection_settings
import laomedo.skills.inspection.utils as _inspection_utils
import laomedo.skills.registry.errors as _registry_errors
import laomedo.skills.registry.store as _registry_store
import laomedo.skills.sources.settings as _sources_settings
import laomedo.skills.sources.errors as _sources_errors
import laomedo.skills.sources.utils as _sources_utils
import os
import re
import signal
import subprocess
import tempfile
import threading
import time


class SkillSources:
    def __init__(self, registry, state, allowed_roots=(), *, repository_provider=None):
        self.store = _registry_store.SkillStore(Path(registry))
        self.state = Path(state).absolute()
        self.state.mkdir(parents=True, exist_ok=True)
        self.allowed_roots = [Path(p).absolute() for p in allowed_roots]
        self.repository_provider = (
            repository_provider  # Trusted test adapter, never an HTTP option.
        )
        self.lock = threading.RLock()
        self.deadline = float("inf")
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
            raise _sources_errors.SourceError("source_required")
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
                raise _sources_errors.SourceError("repository_url_invalid")
            normalized = (
                "https://"
                + parsed.hostname
                + parsed.path.rstrip("/").removesuffix(".git")
                + ".git"
            )
            return "repository", normalized
        if parsed.scheme == "file":
            if (
                parsed.netloc not in {"", "localhost"}
                or parsed.query
                or parsed.fragment
            ):
                raise _sources_errors.SourceError("local_source_invalid")
            value = unquote(parsed.path)
            if os.name == "nt" and re.match(r"^/[A-Za-z]:/", value):
                value = value[1:]
            path = Path(value)
        else:
            path = Path(source)
        if not path.is_absolute():
            raise _sources_errors.SourceError("absolute_local_source_required")
        if path.name == "SKILL.md":
            path = path.parent
        if path == self.store.root:
            return "registry", str(path)
        permitted = next(
            (p for p in self.allowed_roots if path == p or path.is_relative_to(p)), None
        )
        if permitted is None:
            raise _sources_errors.SourceError("local_source_not_allowed")
        # Resolve only after checking every component, including the configured root.
        for component in [path, *path.parents]:
            if is_link(component):
                raise _sources_errors.SourceError("local_source_unsafe")
        if (require_exists and not path.is_dir()) or not path.resolve().is_relative_to(
            permitted.resolve()
        ):
            raise _sources_errors.SourceError("local_source_unavailable")
        return "local", str(path)

    def _git(self, cwd, args, limit=4 * 1024 * 1024):
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper()
            in {
                "PATH",
                "SYSTEMROOT",
                "WINDIR",
                "SYSTEMDRIVE",
                "COMSPEC",
                "PATHEXT",
                "TEMP",
                "TMP",
            }
        }
        env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
            GIT_ASKPASS="",
            SSH_ASKPASS="",
        )
        command = [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.hooksPath=" + str(self.state / "no-hooks"),
            "-c",
            "http.followRedirects=false",
            "-c",
            "protocol.allow=never",
            "-c",
            "protocol.https.allow=always",
            *args,
        ]
        # A trusted fixture adapter may use file transport; it is not exposed by the service.
        if self.repository_provider:
            command[1:1] = ["-c", "protocol.file.allow=always"]
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=os.name != "nt",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
            )
            deadline = min(time.monotonic() + 45, self.deadline)
            try:
                while process.poll() is None:
                    if output.tell() > limit or time.monotonic() > deadline:
                        raise _sources_errors.SourceError("repository_limit_exceeded")
                    if (
                        sum(
                            p.stat().st_size
                            for p in self.state.rglob("*")
                            if p.is_file()
                        )
                        > 128 * 1024 * 1024
                    ):
                        raise _sources_errors.SourceError("repository_limit_exceeded")
                    time.sleep(0.05)
                output.seek(0)
                data = output.read(limit + 1)
                if process.returncode or len(data) > limit:
                    raise _sources_errors.SourceError("repository_access_unavailable")
                return data
            finally:
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    if process.poll() is None:
                        process.kill()
                process.wait()

    def _repository(self, source, refresh=False):
        folder = self.state / hashlib.sha256(source.encode()).hexdigest()
        transport = (
            str(self.repository_provider(source))
            if self.repository_provider
            else source
        )
        if not folder.exists():
            with tempfile.TemporaryDirectory(
                dir=self.state, prefix="clone-"
            ) as temporary:
                pending = Path(temporary) / "repository"
                self._git(
                    self.state,
                    [
                        "clone",
                        "--bare",
                        "--depth=1",
                        "--no-single-branch",
                        "--",
                        transport,
                        str(pending),
                    ],
                )
                pending.rename(folder)
        elif refresh:
            self._git(
                folder,
                [
                    "fetch",
                    "--prune",
                    "--depth=1",
                    "--tags",
                    "origin",
                    "+refs/heads/*:refs/heads/*",
                ],
            )
        refs = (
            self._git(
                folder,
                ["for-each-ref", "--format=%(refname)", "refs/heads", "refs/tags"],
                64 * 1024,
            )
            .decode()
            .splitlines()
        )
        if len(refs) > 32:
            raise _sources_errors.SourceError("repository_limit_exceeded")
        result = []
        for ref in refs:
            commit = (
                self._git(folder, ["rev-parse", "--verify", ref + "^{commit}"], 1024)
                .decode()
                .strip()
            )
            result.append((ref.removeprefix("refs/"), commit))
        if not result:
            raise _sources_errors.SourceError("repository_revision_unavailable")
        return folder, result

    def _entries(self, repo, commit):
        raw = self._git(
            repo, ["ls-tree", "-rz", "--full-tree", commit], 2 * 1024 * 1024
        )
        result = {}
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            header, path = entry.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            path = path.decode("utf-8")
            try:
                validate_relative_path(path)
            except _registry_errors.SkillStoreError:
                raise _sources_errors.SourceError("source_bundle_unsafe") from None
            if any(ord(c) < 32 for c in path):
                raise _sources_errors.SourceError("source_bundle_unsafe")
            if not _sources_utils._excluded(PurePosixPath(path).parts[:-1]):
                if path in result:
                    raise _sources_errors.SourceError("source_bundle_unsafe")
                result[path] = (mode, kind, oid)
            if len(result) > _sources_settings.MAX_ENTRIES:
                raise _sources_errors.SourceError("source_limit_exceeded")
        return result

    def _blob(self, repo, entry):
        mode, kind, oid = entry
        if mode not in {"100644", "100755"} or kind != "blob":
            raise _sources_errors.SourceError("source_bundle_unsafe")
        if (
            int(self._git(repo, ["cat-file", "-s", oid], 128))
            > _inspection_settings.MAX_FILE_BYTES
        ):
            raise _sources_errors.SourceError("source_limit_exceeded")
        return self._git(
            repo, ["cat-file", "blob", oid], _inspection_settings.MAX_FILE_BYTES
        )

    def _local_skills(self, root):
        result = []
        count = 0
        for parent, dirs, files in os.walk(root, followlinks=False):
            if time.monotonic() > self.deadline:
                raise _sources_errors.SourceError("source_limit_exceeded")
            dirs[:] = [d for d in dirs if not _sources_utils._excluded((d,))]
            count += len(dirs) + len(files)
            if (
                count > _sources_settings.MAX_ENTRIES
                or len(Path(parent).relative_to(root).parts) > 16
            ):
                raise _sources_errors.SourceError("source_limit_exceeded")
            if any(is_link(Path(parent) / d) for d in dirs):
                raise _sources_errors.SourceError("local_source_unsafe")
            if "SKILL.md" in files:
                relative = Path(parent).relative_to(root).as_posix()
                name = _sources_utils._name(
                    _inspection_utils._read_regular(
                        Path(parent) / "SKILL.md", _inspection_settings.MAX_FILE_BYTES
                    ),
                    Path(parent).name,
                )
                result.append(
                    {"choice": name + " | " + relative, "name": name, "path": relative}
                )
                if len(result) > 128:
                    raise _sources_errors.SourceError("source_limit_exceeded")
        return result

    def discover(self, source):
        with self.lock:
            self.deadline = time.monotonic() + 60
            kind, location = self._source(source)
            if kind == "registry":
                skills = [
                    {"choice": p.name, "name": p.name, "path": "skills/" + p.name}
                    for p in sorted((self.store.root / "skills").iterdir())
                    if p.is_dir() and not is_link(p)
                ]
            elif kind == "local":
                skills = self._local_skills(Path(location))
            else:
                repo, refs = self._repository(location, refresh=True)
                discovered = {}
                for _, commit in refs:
                    entries = self._entries(repo, commit)
                    for path, entry in entries.items():
                        if PurePosixPath(path).name == "SKILL.md":
                            folder = str(PurePosixPath(path).parent)
                            name = _sources_utils._name(
                                self._blob(repo, entry),
                                PurePosixPath(folder).name or "skill",
                            )
                            choice = name + " | " + folder
                            discovered[choice] = {
                                "choice": choice,
                                "name": name,
                                "path": folder,
                            }
                            if len(discovered) > 128:
                                raise _sources_errors.SourceError(
                                    "source_limit_exceeded"
                                )
                skills = list(discovered.values())
            cached = self.index.setdefault(location, {})
            known = dict(cached.get("skills", {}))
            known.update({s["choice"]: s for s in skills})
            if len(known) > 128:
                raise _sources_errors.SourceError("source_limit_exceeded")
            cached["skills"] = known
            self._save()
            return {
                "kind": kind,
                "skills": sorted(known.values(), key=lambda s: s["choice"]),
            }

    def _register(self, name, files, origin):
        _sources_utils._bundle(files)
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
        return {k: record[k] for k in ("skill_id", "revision_id", "tree_hash")}

    def revisions(self, source, choice):
        with self.lock:
            self.deadline = time.monotonic() + 60
            kind, location = self._source(source)
            cached = self.index.get(location, {})
            skill = cached.get("skills", {}).get(choice)
            if skill is None:
                raise _sources_errors.SourceError("discovered_skill_required")
            if skill["path"] != ".":
                try:
                    validate_relative_path(skill["path"])
                except _registry_errors.SkillStoreError:
                    raise _sources_errors.SourceError("source_bundle_unsafe") from None
            options = dict(cached.get("revisions", {}).get(choice, {}))
            pending = []

            def offer(files, label, origin):
                _sources_utils._bundle(files)
                revision = tree_hash(files)
                reference = {
                    "skill_id": skill["name"],
                    "revision_id": revision,
                    "tree_hash": revision,
                }
                options[label(revision)] = reference
                pending.append((files, origin))

            if kind == "registry":
                for folder in sorted(
                    (self.store._skill(skill["name"]) / "revisions").iterdir()
                ):
                    reference = {
                        "skill_id": skill["name"],
                        "revision_id": "sha256:" + folder.name,
                        "tree_hash": "sha256:" + folder.name,
                    }
                    _inspection_utils.inspect_skill(
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
            elif kind == "local":
                folder = Path(location) / skill["path"]
                if any(is_link(p) for p in [folder, *folder.parents]):
                    raise _sources_errors.SourceError("local_source_unsafe")
                if not (folder / "SKILL.md").exists():
                    return {
                        "revisions": [
                            {"choice": k, **v}
                            for k, v in sorted(options.items(), reverse=True)
                        ]
                    }
                files = {}
                count = 0
                total = 0
                for parent, dirs, names in os.walk(folder, followlinks=False):
                    if time.monotonic() > self.deadline:
                        raise _sources_errors.SourceError("source_limit_exceeded")
                    dirs[:] = [d for d in dirs if not _sources_utils._excluded((d,))]
                    count += len(dirs)
                    if count > 128 or any(is_link(Path(parent) / d) for d in dirs):
                        raise _sources_errors.SourceError("local_source_unsafe")
                    for name in names:
                        if len(files) >= _inspection_settings.MAX_FILES:
                            raise _sources_errors.SourceError("source_limit_exceeded")
                        path = Path(parent) / name
                        _sources_utils._bundle_path(path.relative_to(folder).as_posix())
                        files[path.relative_to(folder).as_posix()] = (
                            _inspection_utils._read_regular(
                                path, _inspection_settings.MAX_FILE_BYTES
                            )
                        )
                        total += len(files[path.relative_to(folder).as_posix()])
                        if total > _inspection_settings.MAX_BUNDLE_BYTES:
                            raise _sources_errors.SourceError("source_limit_exceeded")
                if (
                    _sources_utils._name(files["SKILL.md"], folder.name)
                    == skill["name"]
                ):
                    revision = tree_hash(_sources_utils._bundle(files))
                    if not any(v["revision_id"] == revision for v in options.values()):
                        timestamp = datetime.now(timezone.utc).strftime(
                            "%Y-%m-%d %H:%M:%S UTC"
                        )
                        offer(
                            files,
                            lambda revision: timestamp + " | " + revision,
                            "local: " + location + " / " + skill["path"],
                        )
            else:
                repo, refs = self._repository(location)
                prefix = "" if skill["path"] == "." else skill["path"] + "/"
                for label, commit in refs:
                    entries = self._entries(repo, commit)
                    if prefix + "SKILL.md" not in entries:
                        continue
                    if (
                        _sources_utils._name(
                            self._blob(repo, entries[prefix + "SKILL.md"]),
                            PurePosixPath(skill["path"]).name or "skill",
                        )
                        != skill["name"]
                    ):
                        continue
                    files = {}
                    total = 0
                    for path, entry in entries.items():
                        if path.startswith(prefix):
                            _sources_utils._bundle_path(path[len(prefix) :])
                            if len(files) >= _inspection_settings.MAX_FILES:
                                raise _sources_errors.SourceError(
                                    "source_limit_exceeded"
                                )
                            content = self._blob(repo, entry)
                            total += len(content)
                            if total > _inspection_settings.MAX_BUNDLE_BYTES:
                                raise _sources_errors.SourceError(
                                    "source_limit_exceeded"
                                )
                            files[path[len(prefix) :]] = content
                    offer(
                        files,
                        lambda revision, label=label, commit=commit: label
                        + " @ "
                        + commit
                        + " | "
                        + revision,
                        location + " / " + skill["path"] + " @ " + label + " " + commit,
                    )
            if len(options) > 64:
                raise _sources_errors.SourceError("source_limit_exceeded")
            for files, origin in pending:
                self._register(skill["name"], files, origin)
            cached.setdefault("revisions", {})[choice] = options
            self._save()
            return {
                "revisions": [
                    {"choice": k, **v} for k, v in sorted(options.items(), reverse=True)
                ]
            }

    def resolve(self, source, choice, revision):
        with self.lock:
            _, location = self._source(source, require_exists=False)
            reference = (
                self.index.get(location, {})
                .get("revisions", {})
                .get(choice, {})
                .get(revision)
            )
            if reference is None:
                raise _sources_errors.SourceError("discovered_revision_required")
            label_hash = revision.rsplit(" | ", 1)[-1]
            if (
                label_hash != reference["revision_id"]
                or reference["tree_hash"] != reference["revision_id"]
            ):
                raise _sources_errors.SourceError("source_reference_invalid")
            _inspection_utils.inspect_skill(
                self.store.root, reference["skill_id"], reference["revision_id"]
            )
            return dict(reference)
