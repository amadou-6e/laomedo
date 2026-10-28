"""Authenticated loopback source resolver. No model or GitHub write endpoints."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import laomedo.skills.sources.errors as _sources_errors
import laomedo.skills.sources.service as _sources_service
import secrets


class SkillSourceServer(ThreadingHTTPServer):
    def __init__(self, sources, token, host="127.0.0.1", port=8782):
        if host != "127.0.0.1" or not isinstance(token, str) or len(token) < 32:
            raise ValueError("private_source_service_required")

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass  # Source URLs, filenames and request bodies are not access-log content.

            def reply(self, code, value):
                data = json.dumps(value).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if not secrets.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + token
                ):
                    self.reply(401, {"error_category": "unauthorized"})
                    return
                try:
                    if (
                        self.headers.get("Content-Type", "").split(";")[0]
                        != "application/json"
                    ):
                        raise _sources_errors.SourceError("json_required")
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > 16 * 1024:
                        raise _sources_errors.SourceError("invalid_request")
                    body = json.loads(self.rfile.read(size))
                    if not isinstance(body, dict):
                        raise _sources_errors.SourceError("invalid_request")
                    action = self.path.removeprefix("/v1/skill-sources/")
                    fields = {
                        "discover": {"source"},
                        "revisions": {"source", "skill"},
                        "resolve": {"source", "skill", "revision"},
                    }
                    if (
                        self.path != "/v1/skill-sources/" + action
                        or action not in fields
                        or set(body) != fields[action]
                        or any(
                            not isinstance(v, str) or len(v) > 4096
                            for v in body.values()
                        )
                    ):
                        raise _sources_errors.SourceError("invalid_request")
                    if action == "discover":
                        result = sources.discover(body["source"])
                    elif action == "revisions":
                        result = sources.revisions(body["source"], body["skill"])
                    else:
                        result = sources.resolve(
                            body["source"], body["skill"], body["revision"]
                        )
                    self.reply(200, result)
                except _sources_errors.SourceError as exc:
                    self.reply(400, {"error_category": str(exc)})
                except Exception:
                    # Never export parser errors, Git stderr, local paths or raw file content.
                    self.reply(400, {"error_category": "source_unavailable"})

        super().__init__((host, port), Handler)
