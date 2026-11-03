"""Authenticated loopback boundary for Skill operations; no source/Git writes."""

from http.server import ThreadingHTTPServer
from laomedo.skills.interface.operations.handler import SkillOperationRequestHandler
from laomedo.skills.operations.manual import ManualSkillEditor


class SkillOperationServer(ThreadingHTTPServer):
    """Own the private loopback listener and instance-local service bindings."""

    def __init__(self, operations, token, port=8787, manual_permissions=None):
        """Validate private listener credentials and bind this service/token to one loopback server instance."""
        if not isinstance(token, str) or not 32 <= len(token) <= 512:
            raise ValueError("private_skill_service_required")
        self.operations = operations
        self.manual = ManualSkillEditor(operations, manual_permissions)
        self._token = token
        super().__init__(("127.0.0.1", port), SkillOperationRequestHandler)
