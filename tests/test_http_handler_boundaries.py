"""Internal socket, dependency and extraction controls; no provider acceptance."""

import ast
import hashlib
import json
import importlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import tempfile
import unittest
import runpy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener

from laomedo.github.issues.server import IssueServer
from laomedo.github.issues.contract import ERROR_CODES as ISSUE_CODES
from laomedo.github.pull_requests.server import PullRequestServer
from laomedo.github.pull_requests.contract import ERROR_CODES as PR_CODES
from laomedo.http.redirect import NoRedirect
from laomedo.skills.operations.server import SkillOperationServer
from laomedo.skills.operations.client import skill_request
from laomedo.skills.sources.server import SkillSourceServer
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.client import source_request

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/laomedo"
HANDLERS = {
    "github/issues": "IssueRequestHandler",
    "github/pull_requests": "PullRequestHandler",
    "skills/sources": "SkillSourceRequestHandler",
    "skills/operations": "SkillOperationRequestHandler",
}
CONTRACT_TOOLS = runpy.run_path(str(ROOT / "tools/capture_http_handler_contracts.py"))


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
    @staticmethod
    def retired_bindings(tree):
        """Find executable retired imports, not strings used as migration fixtures."""
        retired = "laomedo.skills.sources.transport"
        modules = {
            "laomedo.github.transport.rest.transport",
            "laomedo.integrations.langflow.join.transport",
        }
        aliases = {}
        failures = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == retired:
                    failures.append(retired)
                if node.module in modules and any(
                    alias.name == "_NoRedirect" for alias in node.names
                ):
                    failures.append(node.module + "._NoRedirect")
                for alias in node.names:
                    imported = (node.module or "") + "." + alias.name
                    if imported in modules:
                        aliases[alias.asname or alias.name] = imported
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == retired:
                        failures.append(retired)
                    if alias.name in modules:
                        aliases[alias.asname or alias.name] = alias.name
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "_NoRedirect":
                owner = ast.unparse(node.value)
                if owner in modules or owner in aliases:
                    failures.append(aliases.get(owner, owner) + "._NoRedirect")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
            ):
                owner = ast.unparse(node.args[0])
                member = node.args[1]
                if (
                    (owner in modules or owner in aliases)
                    and isinstance(member, ast.Constant)
                    and member.value == "_NoRedirect"
                ):
                    failures.append(aliases.get(owner, owner) + "._NoRedirect")
        return failures

    @staticmethod
    def embedded_code(value):
        """Yield embedded code fields from maintained exports, without executing them."""
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                code = item.get("code")
                if isinstance(code, str):
                    yield code
                elif isinstance(code, dict) and isinstance(code.get("value"), str):
                    yield code["value"]
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)

    def test_extracted_handler_control_flow_matches_the_formatted_baseline(self):
        golden = json.loads(
            (ROOT / "tests/contracts/http-handlers-4228872.json").read_text()
        )
        self.assertEqual(golden["baseline"], "422887273038523ca6343234739775b1d218b673")
        for relative, record in golden["handlers"].items():
            self.assertEqual(
                CONTRACT_TOOLS["contract_for_source"](
                    record["baseline_source"], record["service_binding"]
                ),
                record,
                relative,
            )
            folder = SOURCE / relative
            tree = ast.parse((folder / "handler.py").read_text())
            handler = next(node for node in tree.body if isinstance(node, ast.ClassDef))
            handler.name = "Handler"
            if ast.get_docstring(handler):
                handler.body.pop(0)
            observed = CONTRACT_TOOLS["ast_digest"](handler)
            self.assertEqual(observed, record["handler_ast_sha256"], relative)
            server = ast.parse((folder / "server.py").read_text())
            owner = next(node for node in server.body if isinstance(node, ast.ClassDef))
            init = next(
                node for node in owner.body if isinstance(node, ast.FunctionDef)
            )
            admission = next(node for node in init.body if isinstance(node, ast.If))
            self.assertEqual(
                CONTRACT_TOOLS["ast_digest"](admission),
                record["admission_ast_sha256"],
            )
            self.assertEqual(
                CONTRACT_TOOLS["ast_digest"](init.args),
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
        tracked = (
            subprocess.check_output(
                [
                    "git",
                    "-c",
                    f"safe.directory={ROOT.as_posix()}",
                    "ls-files",
                    "-z",
                    "*.py",
                    "examples/*.json",
                ],
                cwd=ROOT,
            )
            .decode()
            .split("\0")
        )
        sealed = {
            record["path"]: record["sha256"]
            for record in json.loads(
                (ROOT / "tools/formatting/historical-sources.json").read_text()
            )
        }
        sealed.update(
            {
                record["historical_original"]: record["sha256"]
                for record in json.loads(
                    (ROOT / "examples/agent-module-history.json").read_text()
                )["files"]
            }
        )
        sealed.update(
            {
                "examples/github-pr/original-agent/historical-flow-before-skill-input.json": "3584ef1108f5be5ddc5b0f7a6f583044fcf31f769874d5368ec86772c63b6b4f",
                "examples/skill-operations/historical-flow-before-skill-input.json": "45ea8e14f22dc52e50e97d367812ad832deb048e1e31e9c58bff8b48c62879cf",
            }
        )
        retained_contract = json.loads(
            (ROOT / "tools/migrations/retained-http-callers.json").read_text()
        )
        retained = {
            record["path"]: record["sha256"] for record in retained_contract["files"]
        }
        for relative in tracked:
            if not relative:
                continue
            path = ROOT / relative
            if relative in sealed:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), sealed[relative]
                )
                continue  # Exact archived runtime source is evidence, not a maintained caller.
            if relative in retained:
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), retained[relative]
                )
                continue  # Preserved caller snapshot; no historical seal-validity claim.
            if path.suffix == ".py":
                snippets = [path.read_text(encoding="utf-8-sig")]
            else:
                snippets = self.embedded_code(
                    json.loads(path.read_text(encoding="utf-8-sig"))
                )
            for snippet in snippets:
                if "laomedo." in snippet:
                    self.assertEqual(
                        self.retired_bindings(ast.parse(snippet)), [], str(path)
                    )

    def test_retained_probe_import_is_only_an_identity_alias(self):
        module = importlib.import_module("laomedo.github.transport.rest.transport")
        contract = json.loads(
            (ROOT / "tools/migrations/retained-http-callers.json").read_text()
        )
        self.assertIs(
            getattr(module, contract["compatibility_symbol"].rsplit(".", 1)[1]),
            NoRedirect,
        )

    def test_retired_symbol_guard_covers_aliases_and_preserves_contract_strings(self):
        for source in (
            "from laomedo.github.transport.rest.transport import _NoRedirect",
            "import laomedo.github.transport.rest.transport as transport\nx = transport._NoRedirect",
            "from laomedo.github.transport.rest import transport\nx = getattr(transport, '_NoRedirect')",
            "from laomedo.skills.sources.transport import NoRedirect",
        ):
            self.assertTrue(self.retired_bindings(ast.parse(source)), source)
        self.assertEqual(
            self.retired_bindings(
                ast.parse(
                    "from laomedo.http.redirect import NoRedirect\nvalue = 'from laomedo.skills.sources.transport import NoRedirect'"
                )
            ),
            [],
        )

    def test_canonical_ast_ignores_only_empty_version_metadata(self):
        tree = ast.parse("class Example:\n    pass\n")
        original = CONTRACT_TOOLS["ast_digest"](tree)
        owner = tree.body[0]
        if "type_params" not in owner._fields:
            owner._fields = (*owner._fields, "type_params")
        owner.type_params = []
        self.assertEqual(CONTRACT_TOOLS["ast_digest"](tree), original)
        owner.type_params = [ast.Name(id="Meaningful", ctx=ast.Load())]
        self.assertNotEqual(CONTRACT_TOOLS["ast_digest"](tree), original)
        self.assertNotEqual(
            CONTRACT_TOOLS["ast_digest"](ast.parse("class Changed:\n    pass\n")),
            original,
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

    def test_skill_clients_keep_existing_http_to_node_error_projection(self):
        for server_type, method, failure, client, arguments, prefix, expected in (
            (
                SkillSourceServer,
                "discover",
                SourceError("local_source_not_allowed"),
                source_request,
                {"source": "source"},
                "LAOMEDO_SKILL_SOURCE",
                "source_discovery_failed",
            ),
            (
                SkillOperationServer,
                "history",
                RuntimeError("private-detail"),
                skill_request,
                {"skill_id": "skill", "revision_id": "revision", "before": ""},
                "LAOMEDO_SKILL_OPERATION",
                "skill_operation_unavailable",
            ),
        ):
            service = Mock()
            getattr(service, method).side_effect = failure
            token = "internal-client-" + "k" * 32
            base = self.start(server_type(service, token, port=0))
            with tempfile.TemporaryDirectory() as temporary:
                token_file = Path(temporary) / "client-token"
                token_file.write_text(token, encoding="utf-8")
                with patch.dict(
                    os.environ,
                    {prefix + "_URL": base, prefix + "_TOKEN_FILE": str(token_file)},
                ):
                    with self.assertRaisesRegex(ValueError, "^" + expected + "$"):
                        client(method, **arguments)


class HandlerCatalogueTests(unittest.TestCase):
    def test_classified_boundary_and_node_codes_have_descriptions_and_existing_recovery(
        self,
    ):
        manifest = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        for group, codes in {
            **manifest["http_boundary_codes"],
            **manifest["node_client_codes"],
        }.items():
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
        )["http_boundary_codes"]
        statuses = {
            "github_http_401",
            "github_http_403",
            "github_http_404",
            "github_http_410",
        }
        self.assertEqual(set(groups["issue_handler"]), set(ISSUE_CODES) | statuses)
        self.assertEqual(set(groups["pr_handler"]), set(PR_CODES) | statuses)

    def test_manifest_distinguishes_actual_node_client_allowlists(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )
        node = manifest["node_client_codes"]
        self.assertEqual(set(node["issue_client"]), set(ISSUE_CODES))
        self.assertEqual(set(node["pr_client"]), set(PR_CODES))
        self.assertIn("github_http_403", node["issue_client"])
        self.assertNotIn("github_http_403", node["pr_client"])
        self.assertNotIn("local_source_not_allowed", node["source_client"])
        self.assertNotIn("skill_operation_refused", node["operation_client"])

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
        self.assertEqual(
            observed, set(manifest["http_boundary_codes"]["source_handler"])
        )
        self.assertEqual(
            manifest["internal_only"]["operation_handler"], ["skill_request_invalid"]
        )

    def test_handler_reply_literals_and_client_failures_cannot_escape_the_guard(self):
        manifest = json.loads(
            (ROOT / "tests/contracts/node-http-error-boundaries.json").read_text()
        )
        public = set().union(
            *map(
                set,
                {
                    **manifest["http_boundary_codes"],
                    **manifest["node_client_codes"],
                }.values(),
            )
        )
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
                            manifest["node_client_codes"][
                                (
                                    "source_client"
                                    if relative.startswith("skills/sources")
                                    else "operation_client"
                                )
                            ],
                            (relative, value.value),
                        )


if __name__ == "__main__":
    unittest.main()
