"""Authenticated loopback boundary for Skill operations; no source/Git writes."""

from http.server import ThreadingHTTPServer
from laomedo.skills.operations.handler import SkillOperationRequestHandler


class SkillOperationServer(ThreadingHTTPServer):
    """Own the private loopback listener and instance-local service bindings."""

    def __init__(self, operations, token, port=8787):
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise ValueError("private_skill_service_required")
        self.operations = operations
        self._token = token
        super().__init__(("127.0.0.1", port), SkillOperationRequestHandler)
