"""Socket and ownership controls; not live graph or authentication acceptance."""

from support.paths import repository_root

import ast
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import unittest
from urllib.error import HTTPError
from urllib.request import build_opener

from support.http_server import RunningHTTPServer
from laomedo.http.redirect import NoRedirect
from laomedo.agents.agents.opencode.auth.transport import NoRedirect as OpenCodeRedirect
from laomedo.host.credentials.siwc.connection import _NoRedirect as ChatGPTRedirect
from laomedo.host.credentials.siwc.errors import AuthError


class RedirectRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.server.requests.append(self.path)
        self.send_response(302 if self.path == "/source" else 200)
        if self.path == "/source":
            self.send_header("Location", "/destination")
        self.end_headers()

    def log_message(self, *_):
        pass


class SharedHTTPTests(unittest.TestCase):
    def test_redirect_is_refused_without_contacting_destination(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectRequestHandler)
        server.requests = []
        with RunningHTTPServer(server):
            for handler in (NoRedirect, NoRedirect()):
                with self.subTest(construction=type(handler).__name__):
                    with self.assertRaises(HTTPError) as found:
                        build_opener(handler).open(
                            f"http://127.0.0.1:{server.server_port}/source", timeout=2
                        )
                    self.assertEqual(found.exception.code, 302)
            self.assertEqual(server.requests, ["/source", "/source"])

    def test_credential_domains_keep_their_distinct_error_codes(self):
        with self.assertRaisesRegex(ValueError, "^opencode_auth_redirect_rejected$"):
            OpenCodeRedirect().redirect_request()
        with self.assertRaisesRegex(AuthError, "^auth_redirect_rejected$"):
            ChatGPTRedirect().redirect_request()

    def test_redirect_owners_and_foreign_feature_dependency(self):
        root = repository_root()
        owners = set()
        for directory in ("src", "components"):
            for path in (root / directory).rglob("*.py"):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name in {
                        "NoRedirect",
                        "_NoRedirect",
                    }:
                        owners.add(path.relative_to(root).as_posix())
                    if isinstance(node, ast.ImportFrom):
                        self.assertNotEqual(
                            node.module, "laomedo.skills.sources.transport"
                        )
                    if isinstance(node, ast.Import):
                        self.assertNotIn(
                            "laomedo.skills.sources.transport",
                            {item.name for item in node.names},
                        )
        self.assertEqual(
            owners,
            {
                "src/laomedo/http/redirect.py",
                # Self-contained components and credential-specific refusals are deliberate.
                "src/laomedo/agents/interface/langflow/component.py",
                "components/laomedo/pr_publisher.py",
                "src/laomedo/agents/agents/opencode/auth/transport.py",
                "src/laomedo/host/credentials/siwc/connection.py",
            },
        )
        self.assertFalse((root / "src/laomedo/skills/sources/transport.py").exists())
