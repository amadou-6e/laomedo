"""Conversation-owned shell files and compare-before-write repository persistence."""

import hashlib
from uuid import UUID

from laomedo.agents.workspaces.models import WorkspaceFiles
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.storage.models import ChatWorkspaceBinding


class ProjectChatWorkspace:
    """Freeze selections on first dispatch; resume the native workspace unchanged."""

    def __init__(self, storage):
        self.storage = storage

    def path(self, owner, conversation):
        return (
            self.storage.root
            / "workspaces"
            / str(UUID(str(owner)))
            / (str(UUID(str(conversation))) + ".json")
        )

    def read(self, owner, conversation):
        path = self.path(owner, conversation)
        if not path.exists():
            return None
        try:
            return ChatWorkspaceBinding.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            raise AssistantError("assistant_storage_unavailable", 503) from None

    def target(self, owner, binding, relative):
        """Resolve only this conversation's frozen locations, with current link checks."""
        if relative.startswith("project/agent-files/") and binding.agent_files:
            location = binding.agent_files
            root = self.storage.child(
                self.storage.checkout(
                    self.storage.document(owner), location.repository_id
                ),
                location.path,
            )
            return self.storage.child(root, relative[len("project/agent-files/") :])
        if relative in binding.graphs:
            return self.storage.graph_path(owner, binding.graphs[relative])
        raise AssistantError("assistant_storage_path_invalid", 422)

    def bind_session(self, owner, conversation, session_key):
        """Refresh only an existing shell binding for this explicitly admitted turn."""
        with self.storage.lock:
            binding = self.read(owner, conversation)
            if binding is not None:
                binding.session_key = session_key
                self.storage.replace(
                    self.path(owner, conversation), binding.model_dump_json().encode()
                )

    def prepare(self, owner, conversation, session_key=None):
        """Persist one bounded initial file set for idempotent fresh dispatch retries."""
        with self.storage.lock:
            prior = self.read(owner, conversation)
            if prior is not None:
                return prior.initial_files
            document = self.storage.document(owner)
            if document.agent_files is None and not document.graphs:
                return WorkspaceFiles()
            binding = ChatWorkspaceBinding(
                agent_files=document.agent_files, session_key=session_key
            )
            content = {}
            listing = self.storage.list_files(owner)
            if listing.get("truncated"):
                raise AssistantError("assistant_storage_limit_reached", 422)
            for relative in listing["agent_files"]:
                path = "project/agent-files/" + relative
                observed = self.storage.read_file(owner, relative)
                content[path] = observed["content"]
                binding.target_hashes[path] = observed["sha256"]
            for identifier, selected in document.graphs.items():
                path = "project/graphs/" + identifier + ".json"
                binding.graphs[path] = selected.location
                observed = self.storage.read_file(owner, "", graph_id=identifier)
                content[path] = observed["content"]
                binding.target_hashes[path] = observed["sha256"]
            try:
                binding.initial_files = WorkspaceFiles(files=content)
            except ValueError:
                raise AssistantError("assistant_storage_limit_reached", 422) from None
            binding.workspace_hashes = {
                path: self.digest(text) for path, text in content.items()
            }
            self.storage.replace(
                self.path(owner, conversation), binding.model_dump_json().encode()
            )
            return binding.initial_files

    def persist(self, owner, conversation, files):
        """Write changed shell files only when their repository baseline still matches."""
        with self.storage.lock:
            binding = self.read(owner, conversation)
            if binding is None:
                return
            hashes = {path: self.digest(text) for path, text in files.files.items()}
            changes = []
            for relative in sorted(hashes.keys() | binding.workspace_hashes.keys()):
                if hashes.get(relative) == binding.workspace_hashes.get(relative):
                    continue
                target = self.target(owner, binding, relative)
                observed = self.storage.digest(target)
                if observed not in (
                    binding.target_hashes.get(relative),
                    hashes.get(relative),
                ):
                    raise AssistantError("assistant_storage_file_changed", 409)
                changes.append((relative, target))
            for relative, target in changes:
                if relative in files.files:
                    self.storage.replace(target, files.files[relative].encode())
                else:
                    try:
                        target.unlink(missing_ok=True)
                    except OSError:
                        raise AssistantError(
                            "assistant_storage_write_failed", 503
                        ) from None
                binding.target_hashes[relative] = hashes.get(relative)
            binding.workspace_hashes = hashes
            self.storage.replace(
                self.path(owner, conversation), binding.model_dump_json().encode()
            )

    @staticmethod
    def digest(text):
        return hashlib.sha256(text.encode()).hexdigest()
