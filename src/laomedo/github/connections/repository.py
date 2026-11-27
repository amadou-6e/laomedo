"""Private GitHub snapshots through bounded object GETs, never a Git subprocess."""

import base64
from hashlib import sha1
from pathlib import PurePosixPath
import re

from laomedo.github.connections.models import (
    GitHubReadAuthorization,
    GitHubSkillRevision,
)
from laomedo.github.connections.settings import GITHUB_REF_LIMIT, GITHUB_TAG_DEPTH
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.settings import MAX_FILES, MAX_FILE_BYTES, MAX_BUNDLE_BYTES
from laomedo.skills.registry.utils.paths import validate_relative_path
from laomedo.skills.sources.bundle import validate_bundle, validate_bundle_path
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.models import (
    PendingSkillImport,
    SkillRepositoryEntry,
    SkillRepositoryRef,
    SkillSourceChoice,
)
from laomedo.skills.sources.settings import MAX_ENTRIES
from laomedo.skills.sources.utils import excluded_parts, skill_name


class GitHubRepositoryReader:
    """Read one authorized generation, within its shared finite request budget."""

    def __init__(self, authorization: GitHubReadAuthorization, client):
        """Require trusted service admission; never construct authorization from JSON."""
        self.authorization = authorization
        self.client = client
        self.client.deadline = min(client.deadline, authorization.deadline)
        self.client.read_bytes = max(client.read_bytes, authorization.consumed_bytes)
        self.base = "/repos/" + authorization.repository.full_name + "/git/"
        self.blobs = {}
        self.trees = {}
        self.references = None

    def _within_budget(self):
        """Cached bytes cannot bypass the admitted operation's total deadline."""
        if self.client.clock() >= self.client.deadline:
            raise SourceError("repository_limit_exceeded")

    def _sha(self, value):
        """Admit only the supported exact SHA-1 object identity, never a ref expression."""
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}", value):
            raise SourceError("source_reference_invalid")
        return value

    async def _peel(self, kind, object_id):
        """Resolve annotated tags with exact object echoes, finite depth and cycle checks."""
        seen = set()
        for _ in range(GITHUB_TAG_DEPTH):
            self._sha(object_id)
            if kind == "commit":
                return object_id
            if kind != "tag" or object_id in seen:
                raise SourceError("source_reference_invalid")
            seen.add(object_id)
            tag = await self.client.get(self.base + "tags/" + object_id)
            if not isinstance(tag, dict) or tag.get("sha") != object_id:
                raise SourceError("source_reference_invalid")
            target = tag.get("object")
            if not isinstance(target, dict):
                raise SourceError("source_reference_invalid")
            kind, object_id = target.get("type"), target.get("sha")
        # Permit exactly the bounded number of tag objects ending at a commit.
        if kind == "commit":
            return self._sha(object_id)
        raise SourceError("source_limit_exceeded")

    async def refs(self):
        """Capture complete heads/tags only; excess or unfinished pages are refused."""
        self._within_budget()
        if self.references is not None:
            return self.references
        raw = []
        labels = set()
        for namespace in ("heads", "tags"):
            response = await self.client.get_page(
                self.base + "matching-refs/" + namespace + "/"
            )
            if response.next_page or not isinstance(response.payload, list):
                raise SourceError("repository_limit_exceeded")
            for item in response.payload:
                if not isinstance(item, dict):
                    raise SourceError("source_reference_invalid")
                label, target = item.get("ref"), item.get("object")
                prefix = "refs/" + namespace + "/"
                if (
                    not isinstance(label, str)
                    or not label.startswith(prefix)
                    or len(label) <= len(prefix)
                    or len(label) > 1024
                    or any(
                        ord(character) < 32 or ord(character) == 127
                        for character in label
                    )
                    or label in labels
                    or not isinstance(target, dict)
                    or (namespace == "heads" and target.get("type") != "commit")
                ):
                    raise SourceError("source_reference_invalid")
                labels.add(label)
                raw.append(
                    (
                        label.removeprefix("refs/"),
                        target.get("type"),
                        self._sha(target.get("sha")),
                    )
                )
                if len(raw) > GITHUB_REF_LIMIT:
                    raise SourceError("repository_limit_exceeded")
        if not raw:
            raise SourceError("repository_revision_unavailable")
        self.references = tuple(
            [
                SkillRepositoryRef(
                    label=label, commit=await self._peel(kind, object_id)
                )
                for label, kind, object_id in raw
            ]
        )
        return self.references

    async def entries(self, commit):
        """Admit a complete exact recursive tree before any Skill blob is returned."""
        self._within_budget()
        commit = self._sha(commit)
        if commit in self.trees:
            return self.trees[commit]
        data = await self.client.get(self.base + "commits/" + commit)
        if (
            not isinstance(data, dict)
            or data.get("sha") != commit
            or not isinstance(data.get("tree"), dict)
        ):
            raise SourceError("source_reference_invalid")
        tree_id = self._sha(data["tree"].get("sha"))
        tree = await self.client.get(
            self.base + "trees/" + tree_id, params={"recursive": "1"}
        )
        if (
            not isinstance(tree, dict)
            or tree.get("sha") != tree_id
            or tree.get("truncated") is not False
            or not isinstance(tree.get("tree"), list)
        ):
            raise SourceError("source_bundle_unsafe")
        if len(tree["tree"]) > MAX_ENTRIES:
            raise SourceError("source_limit_exceeded")
        result, paths = {}, set()
        for item in tree["tree"]:
            if not isinstance(item, dict):
                raise SourceError("source_bundle_unsafe")
            path = item.get("path")
            try:
                validate_relative_path(path)
            except (SkillStoreError, TypeError):
                raise SourceError("source_bundle_unsafe") from None
            if path in paths or any(ord(character) < 32 for character in path):
                raise SourceError("source_bundle_unsafe")
            paths.add(path)
            mode, kind = item.get("mode"), item.get("type")
            object_id = self._sha(item.get("sha"))
            if excluded_parts(PurePosixPath(path).parts[:-1]):
                continue
            if mode == "040000" and kind == "tree":
                continue
            if mode not in {"100644", "100755"} or kind != "blob":
                raise SourceError("source_bundle_unsafe")
            size = item.get("size")
            if type(size) is not int or size < 0:
                raise SourceError("source_bundle_unsafe")
            result[path] = SkillRepositoryEntry(
                mode=mode, kind=kind, object_id=object_id
            )
        self.trees[commit] = result
        return result

    async def read_blob(self, entry):
        """Verify exact regular-file bytes, declared size, base64 and Git blob hash."""
        self._within_budget()
        if entry.mode not in {"100644", "100755"} or entry.kind != "blob":
            raise SourceError("source_bundle_unsafe")
        object_id = self._sha(entry.object_id)
        if object_id in self.blobs:
            return self.blobs[object_id]
        data = await self.client.get(self.base + "blobs/" + object_id)
        if (
            not isinstance(data, dict)
            or data.get("sha") != object_id
            or data.get("encoding") != "base64"
        ):
            raise SourceError("source_bundle_unsafe")
        size, content = data.get("size"), data.get("content")
        if (
            type(size) is not int
            or not 0 <= size <= MAX_FILE_BYTES
            or not isinstance(content, str)
        ):
            raise SourceError("source_limit_exceeded")
        if len(content) > (MAX_FILE_BYTES * 4 // 3 + 4) * 2:
            raise SourceError("source_limit_exceeded")
        try:
            blob = base64.b64decode(
                content.replace("\r", "").replace("\n", ""), validate=True
            )
        except (ValueError, UnicodeError):
            raise SourceError("source_bundle_unsafe") from None
        if (
            len(blob) != size
            or sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()
            != object_id
        ):
            raise SourceError("source_reference_invalid")
        self.blobs[object_id] = blob
        return blob

    async def discover(self):
        """Reuse canonical Skill frontmatter/name choices across bounded ref snapshots."""
        result = {}
        for ref in await self.refs():
            for path, entry in (await self.entries(ref.commit)).items():
                if PurePosixPath(path).name != "SKILL.md":
                    continue
                folder = str(PurePosixPath(path).parent)
                name = skill_name(
                    await self.read_blob(entry), PurePosixPath(folder).name or "skill"
                )
                choice = SkillSourceChoice.for_folder(name, folder)
                result[choice.choice] = choice
                if len(result) > MAX_FILES:
                    raise SourceError("source_limit_exceeded")
        self._within_budget()
        return tuple(sorted(result.values(), key=lambda item: item.choice))

    async def revisions(self, choice: SkillSourceChoice):
        """Collect and validate exact candidate bundles without publishing any bytes."""
        if choice.path != ".":
            validate_bundle_path(choice.path)
        prefix = "" if choice.path == "." else choice.path + "/"
        result = []
        for ref in await self.refs():
            entries = await self.entries(ref.commit)
            instruction = entries.get(prefix + "SKILL.md")
            if instruction is None:
                continue
            if (
                skill_name(
                    await self.read_blob(instruction),
                    PurePosixPath(choice.path).name or "skill",
                )
                != choice.name
            ):
                continue
            files, total = {}, 0
            for path, entry in entries.items():
                if not path.startswith(prefix):
                    continue
                relative = path[len(prefix) :]
                validate_bundle_path(relative)
                if len(files) >= MAX_FILES:
                    raise SourceError("source_limit_exceeded")
                content = await self.read_blob(entry)
                total += len(content)
                if total > MAX_BUNDLE_BYTES:
                    raise SourceError("source_limit_exceeded")
                files[relative] = content
            validate_bundle(files)
            result.append(
                GitHubSkillRevision(
                    label=ref.label,
                    commit=ref.commit,
                    candidate=PendingSkillImport(
                        files=files,
                        origin=(
                            "https://github.com/"
                            + self.authorization.repository.full_name
                            + " / "
                            + choice.path
                            + " @ "
                            + ref.label
                            + " "
                            + ref.commit
                        ),
                    ),
                )
            )
        self._within_budget()
        return tuple(result)
