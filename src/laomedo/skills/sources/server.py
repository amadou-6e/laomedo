"""Authenticated loopback source resolver. No model or GitHub write endpoints."""

from http.server import ThreadingHTTPServer
from laomedo.skills.sources.handler import SkillSourceRequestHandler


class SkillSourceServer(ThreadingHTTPServer):
    """Own the private loopback listener and instance-local service bindings."""

    def __init__(self, sources, token, host="127.0.0.1", port=8782):
        if host != '127.0.0.1' or not isinstance(token, str) or len(token) < 32:
            raise ValueError('private_source_service_required')
        self.sources = sources
        self._token = token
        super().__init__((host, port), SkillSourceRequestHandler)
