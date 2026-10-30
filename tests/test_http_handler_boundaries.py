"""Internal socket, dependency and extraction controls; no provider acceptance."""

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from laomedo.github.issues.server import IssueServer
from laomedo.github.issues.contract import ERROR_CODES as ISSUE_CODES
from laomedo.github.pull_requests.server import PullRequestServer
from laomedo.github.pull_requests.contract import ERROR_CODES as PR_CODES
from laomedo.http.redirect import NoRedirect
from laomedo.skills.operations.server import SkillOperationServer
from laomedo.skills.sources.server import SkillSourceServer
from laomedo.skills.sources.errors import SourceError

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/laomedo"
HANDLERS = {
    "github/issues": "IssueRequestHandler",
    "github/pull_requests": "PullRequestHandler",
    "skills/sources": "SkillSourceRequestHandler",
    "skills/operations": "SkillOperationRequestHandler",
}


class RedirectControlHandler(BaseHTTPRequestHandler):
    """Local credential-free control recording whether a redirect was followed."""

    def log_message(self, *_):
        pass

    def do_GET(self):
        self.server.visits.append(self.path)
        self.send_response(302 if self.path == "/initial" else 200)
        if self.path == "/initial":
            self.send_header("Location", "/final")
        self.send_header("Content-Length", "0")
        self.end_headers()


class HandlerStructureTests(unittest.TestCase):
    def test_extracted_handler_control_flow_matches_the_formatted_baseline(self):
        golden = json.loads(
            (ROOT / "tests/contracts/http-handlers-4228872.json").read_text()
        )
        self.assertEqual(golden["baseline"], "422887273038523ca6343234739775b1d218b673")
        for relative, record in golden["handlers"].items():
            folder = SOURCE / relative
            tree = ast.parse((folder / "handler.py").read_text())
            handler = next(node for node in tree.body if isinstance(node, ast.ClassDef))
            handler.name = "Handler"
            if ast.get_docstring(handler):
                handler.body.pop(0)
            observed = hashlib.sha256(ast.dump(handler).encode()).hexdigest()
            self.assertEqual(observed, record["handler_ast_sha256"], relative)
            server = ast.parse((folder / "server.py").read_text())
            owner = next(node for node in server.body if isinstance(node, ast.ClassDef))
            init = next(
                node for node in owner.body if isinstance(node, ast.FunctionDef)
            )
            admission = next(node for node in init.body if isinstance(node, ast.If))
            self.assertEqual(
                hashlib.sha256(ast.dump(admission).encode()).hexdigest(),
                record["admission_ast_sha256"],
            )
            self.assertEqual(
                hashlib.sha256(ast.dump(init.args).encode()).hexdigest(),
                record["arguments_ast_sha256"],
            )

    def test_reworked_modules_have_no_nested_classes_or_domain_module_aliases(self):
        paths = [
            SOURCE / relative / name
            for relative in HANDLERS
            for name in ("handler.py", "server.py")
        ]
        paths += [
            SOURCE / path
            for path in (
                "github/issues/client.py",
                "github/pull_requests/client.py",
                "skills/sources/client.py",
                "skills/operations/client.py",
                "github/transport/rest/transport.py",
                "integrations/langflow/join/transport.py",
                "http/redirect.py",
            )
        ]
        for path in paths:
            tree = ast.parse(path.read_text())
            top = {id(node) for node in tree.body}
            self.assertFalse(
                [
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.ClassDef) and id(node) not in top
                ],
                str(path),
            )
            self.assertFalse(
                [
                    alias.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.Import)
                    for alias in node.names
                    if alias.name.startswith("laomedo.")
                ],
                str(path),
            )

    def test_redirect_definitions_are_canonical_or_named_credential_component_exceptions(
        self,
    ):
        owners = set()
        for path in [
            *SOURCE.rglob("*.py"),
            *(ROOT / "components/laomedo").glob("*.py"),
        ]:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ClassDef) and any(
                    getattr(base, "id", getattr(base, "attr", ""))
                    == "HTTPRedirectHandler"
                    for base in node.bases
                ):
                    owners.add(path.relative_to(ROOT).as_posix())
        self.assertEqual(
            owners,
            {
                "src/laomedo/http/redirect.py",
                "src/laomedo/agents/interface/langflow/component.py",
                "components/laomedo/pr_publisher.py",
                "src/laomedo/host/credentials/siwc/connection.py",
                "src/laomedo/agents/agents/opencode/auth/transport.py",
            },
        )

    def test_retired_redirect_targets_are_flat_and_no_active_import_remains(self):
        modules = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
        symbols = json.loads((ROOT / "tools/migrations/symbol-paths.json").read_text())
        retired = "laomedo.skills.sources.transport"
        self.assertFalse((SOURCE / "skills/sources/transport.py").exists())
        self.assertEqual(modules[retired], "laomedo.http.redirect")
        for old in (
            retired + ".NoRedirect",
            "laomedo.github.transport.rest.transport._NoRedirect",
            "laomedo.integrations.langflow.join.transport._NoRedirect",
        ):
            self.assertEqual(symbols[old], "laomedo.http.redirect.NoRedirect")
        self.assertFalse(
            any(
                value.startswith(retired)
                for value in [*modules.values(), *symbols.values()]
            )
        )
        for path in SOURCE.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if isinstance(node, ast.ImportFrom):
                    self.assertNotEqual(node.module, retired, str(path))
                elif isinstance(node, ast.Import):
                    self.assertFalse(
                        any(alias.name == retired for alias in node.names), str(path)
                    )

    def test_skill_clients_stay_domain_leafs_and_use_this_worktree(self):
        script = """
import importlib, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root / 'src'))
for name in ('laomedo.skills.sources.client', 'laomedo.skills.operations.client', 'laomedo.http.redirect'):
    module = importlib.import_module(name)
    assert pathlib.Path(module.__file__).resolve().is_relative_to(root), module.__file__
for prefix in ('laomedo.host', 'laomedo.agents', 'laomedo.github', 'laomedo.work_graph', 'langflow', 'lfx'):
    assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules), prefix
"""
        result = subprocess.run(
            [sys.executable, "-c", script, str(ROOT)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class HandlerSocketTests(unittest.TestCase):
    def start(self, server):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return "http://127.0.0.1:" + str(server.server_port)

    def post(self, base, route, token, body, content_type="application/json"):
        call = Request(
            base + route,
            data=json.dumps(body).encode(),
            headers={"Authorization": "Bearer " + token, "Content-Type": content_type},
        )
        try:
            response = build_opener(NoRedirect()).open(call, timeout=5)
        except HTTPError as response:
            return response.code, json.loads(response.read()), response.headers
        with response:
            return response.status, json.loads(response.read()), response.headers

    def test_all_four_servers_isolate_credentials_and_service_bindings(self):
        for server_type, route, body, method in (
            (
                IssueServer,
                "/v1/github-issues/discover",
                {
                    "repository_url": "https://github.com/owner/repo",
                    "labels": [],
                    "state": "open",
                },
                "discover",
            ),
            (
                PullRequestServer,
                "/v1/github-prs/discover",
                {
                    "repository_url": "https://github.com/owner/repo",
                    "labels": [],
                    "state": "open",
                },
                "discover",
            ),
            (
                SkillSourceServer,
                "/v1/skill-sources/discover",
                {"source": "source"},
                "discover",
            ),
            (
                SkillOperationServer,
                "/v1/skill-operations/history",
                {"skill_id": "skill", "revision_id": "revision", "before": ""},
                "history",
            ),
        ):
            services = [Mock(), Mock()]
            tokens = ["control-one-" + "a" * 32, "control-two-" + "b" * 32]
            for index, service in enumerate(services):
                getattr(service, method).return_value = {"instance": index}
            bases = [
                self.start(server_type(service, token, port=0))
                for service, token in zip(services, tokens)
            ]
            for index, base in enumerate(bases):
                refused = self.post(base, route, tokens[1 - index], body)
                self.assertEqual(refused[:2], (401, {"error_category": "unauthorized"}))
                getattr(services[index], method).assert_not_called()
                accepted = self.post(base, route, tokens[index], body)
                self.assertEqual(accepted[:2], (200, {"instance": index}))
                self.assertEqual(accepted[2]["Cache-Control"], "no-store")
                self.assertNotIn(tokens[index], json.dumps(accepted[1]))

    def test_redirect_is_refused_without_forwarding(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectControlHandler)
        server.visits = []
        base = self.start(server)
        for handler in (NoRedirect, NoRedirect()):
            with self.assertRaises(HTTPError) as error:
                build_opener(handler).open(base + "/initial", timeout=5)
            self.assertEqual(error.exception.code, 302)
        self.assertEqual(server.visits, ["/initial", "/initial"])

    def test_unknown_failures_preserve_safe_fallback_and_uncertain_writes(self):
        for server_type, route, body, method, expected_status, expected_code in (
            (
                IssueServer,
                "/v1/github-issues/execute",
                {
                    "repository_url": "https://github.com/owner/repo",
                    "labels": [],
                    "state": "open",
                    "issue_number": 1,
                    "operation": {"action": "close"},
                },
                "execute",
                503,
                "issue_write_unknown",
            ),
            (
                PullRequestServer,
                "/v1/github-prs/apply-feedback",
                {"ticket": "private-ticket", "operation": {"action": "close"}},
                "apply_feedback",
                503,
                "pr_write_unknown",
            ),
            (
                SkillSourceServer,
                "/v1/skill-sources/discover",
                {"source": "source"},
                "discover",
                400,
                "source_unavailable",
            ),
            (
                SkillOperationServer,
                "/v1/skill-operations/history",
                {"skill_id": "skill", "revision_id": "revision", "before": ""},
                "history",
                400,
                "skill_operation_refused",
            ),
        ):
            service = Mock()
            getattr(service, method).side_effect = RuntimeError(
                "private-payload private-token /private/path"
            )
            token = "internal-control-" + "x" * 32
            base = self.start(server_type(service, token, port=0))
            status, result, _ = self.post(base, route, token, body)
            self.assertEqual(
                (status, result), (expected_status, {"error_category": expected_code})
            )
            self.assertNotIn("private", json.dumps(result))
            getattr(service, method).assert_called_once()

    def test_source_domain_codes_are_preserved_without_exporting_unknown_errors(self):
        service = Mock()
        service.discover.side_effect = SourceError("local_source_not_allowed")
        token = "internal-control-" + "s" * 32
        base = self.start(SkillSourceServer(service, token, port=0))
        status, result, _ = self.post(
            base, "/v1/skill-sources/discover", token, {"source": "source"}
        )
        self.assertEqual(
            (status, result), (400, {"error_category": "local_source_not_allowed"})
        )


class HandlerCatalogueTests(unittest.TestCase):
    def test_classified_public_codes_have_descriptions_and_existing_recovery(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        for group, codes in manifest["public_codes"].items():
            for code in codes:
                self.assertIn(code, catalogue, (group, code))
                for field in ("title", "description", "recovery"):
                    self.assertTrue(
                        catalogue[code][field].strip(), (group, code, field)
                    )
        for code in (
            "issue_write_unknown",
            "pr_write_unknown",
            "skill_operation_unavailable",
        ):
            self.assertIn("before", catalogue[code]["recovery"])
        self.assertIn(
            "Do not blindly repeat", catalogue["pr_write_unknown"]["recovery"]
        )

    def test_code_guard_tracks_actual_issue_and_pr_handler_contracts(self):
        groups = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )["public_codes"]
        statuses = {
            "github_http_401",
            "github_http_403",
            "github_http_404",
            "github_http_410",
        }
        self.assertEqual(set(groups["issue_handler"]), set(ISSUE_CODES) | statuses)
        self.assertEqual(set(groups["pr_handler"]), set(PR_CODES) | statuses)

    def test_source_guard_follows_domain_passthrough_and_safe_fallbacks(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )
        observed = {"unauthorized", "source_unavailable"}
        for path in (SOURCE / "skills/sources").glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not (
                    isinstance(node, ast.Raise)
                    and isinstance(node.exc, ast.Call)
                    and node.exc.args
                ):
                    continue
                category = getattr(
                    node.exc.func, "id", getattr(node.exc.func, "attr", "")
                )
                argument = node.exc.args[0]
                if category == "SourceError":
                    self.assertIsInstance(argument, ast.Constant, str(path))
                    self.assertIsInstance(argument.value, str, str(path))
                if (
                    category == "SourceError"
                    and isinstance(argument, ast.Constant)
                    and isinstance(argument.value, str)
                ):
                    observed.add(argument.value)
        self.assertEqual(observed, set(manifest["public_codes"]["source_handler"]))
        self.assertEqual(
            manifest["internal_only"]["operation_handler"], ["skill_request_invalid"]
        )

    def test_handler_reply_literals_and_client_failures_cannot_escape_the_guard(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )
        public = set().union(*map(set, manifest["public_codes"].values()))
        for relative in HANDLERS:
            path = SOURCE / relative / "handler.py"
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Dict):
                    for key, value in zip(node.keys, node.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "error_category"
                            and isinstance(value, ast.Constant)
                        ):
                            self.assertIn(value.value, public, (relative, value.value))
        for relative in ("skills/sources/client.py", "skills/operations/client.py"):
            for node in ast.walk(ast.parse((SOURCE / relative).read_text())):
                if (
                    isinstance(node, ast.Raise)
                    and isinstance(node.exc, ast.Call)
                    and node.exc.args
                ):
                    value = node.exc.args[0]
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        self.assertIn(
                            value.value,
                            manifest["public_codes"]["skill_clients"],
                            (relative, value.value),
                        )


if __name__ == "__main__":
    unittest.main()
