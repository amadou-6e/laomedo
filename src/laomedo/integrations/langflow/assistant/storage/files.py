"""Local checkout selections and bounded, compare-before-write project files."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from laomedo.agents.workspaces.utils import is_link
import tempfile
import threading
from uuid import UUID, uuid4

from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.models import (
    GraphFileBinding,
    RepositoryConnection,
    StorageDocument,
)


class ProjectStorage:
    """Single local app process owns configuration and selected file operations."""

    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.RLock()

    def document_path(self, owner):
        """Use canonical UUID identity rather than caller-controlled filenames."""
        return self.root / (str(UUID(str(owner))) + ".json")

    def document(self, owner):
        """Read only app-owned metadata; corruption never becomes empty settings."""
        path = self.document_path(owner)
        try:
            if not path.exists():
                return StorageDocument()
            return StorageDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise AssistantError("assistant_storage_unavailable", 503) from None

    def replace(self, path, content):
        """Replace one file atomically, retaining its old contents on write failure."""
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        except OSError:
            raise AssistantError("assistant_storage_write_failed", 503) from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def save_document(self, owner, document):
        self.replace(
            self.document_path(owner), document.model_dump_json(indent=2).encode()
        )

    def unsafe(self, part):
        """Refuse metadata, common secrets and platform-specific alternate paths."""
        lower = part.lower()
        return (
            lower
            in {
                "",
                ".",
                "..",
                ".git",
                ".ssh",
                ".codex",
                ".claude",
                ".aws",
                ".tools",
                ".venv",
                "node_modules",
            }
            or lower.startswith(".laomedo")
            or lower.startswith(".env")
            or lower in {"auth.json", "credentials.json", "id_rsa", "id_ed25519"}
            or ":" in part
            or "\\" in part
            or "\x00" in part
            or part.endswith((".", " "))
        )

    def child(self, root, relative):
        """Reject lexical escapes and every existing link/reparse component."""
        parts = relative.split("/")
        if PurePosixPath(relative).is_absolute() or any(self.unsafe(p) for p in parts):
            raise AssistantError("assistant_storage_path_invalid", 422)
        path = root
        for part in parts:
            path = path / part
            if is_link(path):
                raise AssistantError("assistant_storage_path_invalid", 422)
        if not path.resolve().is_relative_to(root.resolve()):
            raise AssistantError("assistant_storage_path_invalid", 422)
        return path

    def checkout(self, document, identifier):
        repository = next(
            (r for r in document.repositories if r.id == identifier), None
        )
        if repository is None:
            raise AssistantError("assistant_storage_repository_missing", 404)
        path = Path(repository.path)
        if not path.is_dir() or not (path / ".git").exists():
            raise AssistantError("assistant_storage_repository_unavailable", 409)
        # Recheck ancestors when using retained registrations, including junctions.
        if any(is_link(p) for p in (path, *path.parents)):
            raise AssistantError("assistant_storage_path_invalid", 422)
        return path

    def register(self, owner, request):
        with self.lock:
            path = Path(request.path)
            if not path.is_absolute() or str(path).startswith("\\\\"):
                raise AssistantError("assistant_storage_path_invalid", 422)
            if any(is_link(p) for p in (path, *path.parents)):
                raise AssistantError("assistant_storage_path_invalid", 422)
            path = path.resolve()
            if not path.is_dir() or not (path / ".git").exists():
                raise AssistantError("assistant_storage_repository_unavailable", 409)
            document = self.document(owner)
            if any(Path(item.path) == path for item in document.repositories):
                return self.describe(owner)
            if len(document.repositories) >= 30:
                raise AssistantError("assistant_storage_limit_reached", 422)
            document.repositories.append(
                RepositoryConnection(id=uuid4(), name=request.name, path=str(path))
            )
            self.save_document(owner, document)
            return self.describe(owner)

    def configure_agent_files(self, owner, location):
        with self.lock:
            document = self.document(owner)
            root = self.checkout(document, location.repository_id)
            path = self.child(root, location.path)
            if any(
                path
                == self.child(
                    self.checkout(document, item.location.repository_id),
                    item.location.path,
                )
                or path
                in self.child(
                    self.checkout(document, item.location.repository_id),
                    item.location.path,
                ).parents
                for item in document.graphs.values()
            ):
                raise AssistantError("assistant_storage_location_conflict", 409)
            path.mkdir(parents=True, exist_ok=True)
            document.agent_files = location
            self.save_document(owner, document)
            return self.describe(owner)

    def graph_path(self, owner, location, *, document=None):
        document = document if document is not None else self.document(owner)
        path = self.child(
            self.checkout(document, location.repository_id), location.path
        )
        if path.suffix.lower() != ".json":
            raise AssistantError("assistant_storage_path_invalid", 422)
        if document.agent_files:
            agent = document.agent_files
            directory = self.child(
                self.checkout(document, agent.repository_id), agent.path
            )
            if path == directory or directory in path.parents:
                raise AssistantError("assistant_storage_location_conflict", 409)
        return path

    def digest(self, path):
        try:
            if not path.exists():
                return None
            if not path.is_file() or path.stat().st_size > 262144:
                raise AssistantError("assistant_storage_file_too_large", 422)
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise AssistantError("assistant_storage_unavailable", 503) from None

    def bind_graph(self, owner, identifier, location, digest):
        document = self.document(owner)
        document.graphs[str(identifier)] = GraphFileBinding(
            location=location, sha256=digest
        )
        self.save_document(owner, document)

    def describe(self, owner):
        result = self.document(owner).model_dump(mode="json")
        for binding in result["graphs"].values():
            from laomedo.integrations.langflow.assistant.storage.models import (
                RepositoryLocation,
            )

            try:
                path = self.graph_path(
                    owner, RepositoryLocation.model_validate(binding["location"])
                )
                binding["current_sha256"] = self.digest(path)
                binding["availability"] = "available" if path.exists() else "missing"
            except AssistantError as error:
                binding["current_sha256"] = None
                binding["availability"] = error.code
        return result

    def agent_path(self, owner, relative, *, document=None):
        document = document if document is not None else self.document(owner)
        if document.agent_files is None:
            raise AssistantError("assistant_storage_agent_files_not_configured", 409)
        location = document.agent_files
        directory = self.child(
            self.checkout(document, location.repository_id), location.path
        )
        return self.child(directory, relative)

    def list_files(self, owner, *, document=None):
        """Expose only selected file names, never host paths or whole checkouts."""
        with self.lock:
            document = document if document is not None else self.document(owner)
            result = {"agent_files": [], "graph_files": list(document.graphs)}
            if document.agent_files:
                location = document.agent_files
                directory = self.child(
                    self.checkout(document, location.repository_id), location.path
                )
                if directory.is_dir():
                    pending = [directory]
                    scanned = 0
                    while pending and scanned < 1000:
                        current = pending.pop()
                        for item in current.iterdir():
                            scanned += 1
                            if scanned > 1000:
                                break
                            if self.unsafe(item.name) or is_link(item):
                                continue
                            if item.is_dir():
                                pending.append(item)
                            elif item.is_file():
                                result["agent_files"].append(
                                    item.relative_to(directory).as_posix()
                                )
                    result["truncated"] = bool(pending) or scanned >= 1000
            return result

    def read_file(self, owner, relative, graph_id=None, *, document=None):
        with self.lock:
            document = document if document is not None else self.document(owner)
            if graph_id:
                binding = document.graphs.get(str(UUID(graph_id)))
                if binding is None:
                    raise AssistantError("assistant_storage_graph_not_connected", 404)
                path = self.graph_path(owner, binding.location, document=document)
            else:
                path = self.agent_path(owner, relative, document=document)
            digest = self.digest(path)
            if digest is None:
                raise AssistantError("assistant_storage_file_missing", 404)
            try:
                text = path.read_bytes().decode("utf-8")
            except (OSError, UnicodeError):
                raise AssistantError("assistant_storage_text_required", 422) from None
            return {
                "path": relative if not graph_id else "graph:" + graph_id,
                "content": text,
                "sha256": digest,
            }

    def write_file(self, owner, request, *, document=None):
        with self.lock:
            path = self.agent_path(owner, request.path, document=document)
            if self.digest(path) != request.expected_sha256:
                raise AssistantError("assistant_storage_file_changed", 409)
            self.replace(path, request.content.encode("utf-8"))
            return {"path": request.path, "sha256": self.digest(path)}
