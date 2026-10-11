"""Explicit host-only credential source for the bounded GitHub live probe.

This is not browser login or a production secret vault. It reads one named
key from a user-provided file in the credential-owning service, never from
ambient gh, Git Credential Manager, or a runner environment. Replacing or
removing the file invalidates the generation loaded at service startup.
"""

from __future__ import annotations

import hmac
from pathlib import Path


class HostTokenConnection:
    def __init__(self, *, connection_id: str, generation: int,
                 repository: str, token_file: str | Path, key: str = "GH",
                 forbidden_mount: str | Path | None = None):
        if (not isinstance(connection_id, str) or not connection_id or
                type(generation) is not int or generation < 1 or
                not isinstance(repository, str) or "/" not in repository or
                not isinstance(key, str) or not key.isidentifier()):
            raise ValueError("connection_invalid")
        path = Path(token_file).expanduser()
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("credential_file_invalid")
        self.path = path.resolve()
        if forbidden_mount is not None and self.path.is_relative_to(
                Path(forbidden_mount).resolve()):
            raise ValueError("credential_inside_agent_mount")
        self.connection_id = connection_id
        self.generation = generation
        self.repository = repository
        self.key = key
        self._token = self._read_token()

    def _read_token(self) -> str:
        if self.path.is_symlink() or not self.path.is_file():
            raise ValueError("credential_file_unavailable")
        values = []
        for line in self.path.read_text(encoding="utf-8-sig").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == self.key:
                candidate = value.strip()
                if len(candidate) >= 2 and candidate[0] == candidate[-1] and \
                        candidate[0] in {"'", '"'}:
                    candidate = candidate[1:-1]
                values.append(candidate)
        if len(values) != 1 or not values[0] or any(
                character in values[0] for character in "\r\n\0"):
            raise ValueError("credential_file_unavailable")
        return values[0]

    def current(self, connection_id: str, generation: int,
                repository: str) -> bool:
        if (connection_id, generation, repository) != (
                self.connection_id, self.generation, self.repository):
            return False
        try:
            return hmac.compare_digest(self._read_token(), self._token)
        except (OSError, UnicodeError, ValueError):
            return False

    def authorize(self, connection_id: str, generation: int,
                  repository: str, reviewed_by: str) -> bool:
        return bool(reviewed_by) and self.current(connection_id, generation,
                                                  repository)

    def token(self, connection_id: str, generation: int) -> str:
        if not self.current(connection_id, generation, self.repository):
            raise KeyError("connection_unavailable")
        return self._token
