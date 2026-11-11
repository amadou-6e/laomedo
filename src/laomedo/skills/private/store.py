"""Immutable private bundles with owner/connection/repository provenance."""

from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from laomedo.github.connections.errors import GitHubRepositoryAccessError
from laomedo.github.connections.models import (
    GitHubReadAuthorization,
    GitHubSkillRevision,
)
from laomedo.skills.private.models import PrivateSkillOrigin
from laomedo.skills.registry.store import SkillStore
from laomedo.skills.registry.utils.files import is_link, read_json, write_json
from laomedo.skills.registry.utils.inspection import inspect_skill
from laomedo.skills.sources.bundle import validate_bundle
from laomedo.skills.sources.models import SkillSourceChoice


class PrivateSkillStore:
    """Retain private bytes only in a trusted root supplied by the native runtime."""

    def __init__(self, root: Path):
        self.root = root.absolute()

    def _namespace(self, authorization: GitHubReadAuthorization):
        path = (
            self.root
            / str(authorization.owner_id)
            / str(authorization.connection_id)
            / str(authorization.repository.id)
        )
        for checked in (path, *path.parents):
            if is_link(checked) or (checked / ".git").exists():
                raise GitHubRepositoryAccessError()
        return path

    def _origin_path(self, namespace, origin):
        key = sha256(origin.model_dump_json().encode()).hexdigest()
        return namespace / "origins" / (key + ".json")

    def retain(
        self,
        authorization: GitHubReadAuthorization,
        choice: SkillSourceChoice,
        revision: GitHubSkillRevision,
    ):
        """Publish immutable bytes before committing their exact provenance pointer."""
        validate_bundle(revision.candidate.files)
        namespace = self._namespace(authorization)
        store = SkillStore(namespace / "registry", namespace / "drafts")
        skill_id = "private-" + sha256(choice.choice.encode()).hexdigest()[:48]
        with TemporaryDirectory(dir=namespace, prefix="import-") as temporary:
            source = Path(temporary)
            for relative, content in revision.candidate.files.items():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            if (store._skill(skill_id) / "latest.json").exists():
                record = store._store_revision(skill_id, source, None)
            else:
                record = store.import_skill(skill_id, source)
        origin = PrivateSkillOrigin(
            owner_id=authorization.owner_id,
            connection_id=authorization.connection_id,
            repository_id=authorization.repository.id,
            choice=choice,
            skill_id=skill_id,
            revision_id=record["revision_id"],
            commit=revision.commit,
            label=revision.label,
        )
        destination = self._origin_path(namespace, origin)
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_json(destination, origin.model_dump(mode="json"))
        return origin

    def origins(self, authorization: GitHubReadAuthorization):
        """Read only this authorized namespace; refuse corrupt or redirected pointers."""
        namespace = self._namespace(authorization)
        directory = namespace / "origins"
        if is_link(directory):
            raise GitHubRepositoryAccessError()
        result = []
        try:
            for path in sorted(directory.glob("*.json")):
                if is_link(path) or path.stat().st_size > 16384:
                    raise GitHubRepositoryAccessError()
                origin = PrivateSkillOrigin.model_validate(read_json(path))
                if (
                    origin.owner_id != authorization.owner_id
                    or origin.connection_id != authorization.connection_id
                    or origin.repository_id != authorization.repository.id
                    or path != self._origin_path(namespace, origin)
                ):
                    raise GitHubRepositoryAccessError()
                result.append(origin)
        except (OSError, ValueError, ValidationError):
            raise GitHubRepositoryAccessError() from None
        return tuple(result)

    def inspect(self, authorization, skill_id, revision_id):
        """Require recorded private provenance before reading even matching hashes."""
        if not any(
            origin.skill_id == skill_id and origin.revision_id == revision_id
            for origin in self.origins(authorization)
        ):
            raise GitHubRepositoryAccessError()
        return inspect_skill(
            self._namespace(authorization) / "registry",
            skill_id,
            revision_id,
            include_images=True,
            include_binary=True,
        )
