"""Cover Agent errors and the affected runner skill-validation producers."""

import ast
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def producer_paths(filename):
    module = "laomedo." + Path(filename).stem
    mapping = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())
    symbols = json.loads((ROOT / "tools/migrations/symbol-paths.json").read_text())
    prefix = mapping[module].rsplit(".", 1)[0] + "."
    owners = {mapping[module]} | {
        value.rsplit(".", 1)[0]
        for key, value in symbols.items()
        if key.startswith(module + ".")
        and value.startswith(prefix)
        and not value in mapping.values()
    }
    owners.update(
        ".".join(path.relative_to(ROOT / "src").with_suffix("").parts)
        for path in ROOT.joinpath("src", *mapping[module].split(".")[:-1]).glob("*.py")
        if path.name != "__init__.py"
    )
    if filename == "local_runner.py":
        owners.update(
            {"laomedo.agents.agents.base.agent", "laomedo.agents.agents.base.utils"}
        )
    paths = sorted(
        ROOT.joinpath("src", *owner.split(".")).with_suffix(".py") for owner in owners
    )
    if not paths or any(not path.is_file() for path in paths):
        raise AssertionError("Missing defining error producer: " + module)
    return paths


def producer_path(filename):
    module = json.loads((ROOT / "tools/migrations/module-paths.json").read_text())[
        "laomedo." + Path(filename).stem
    ]
    return ROOT.joinpath("src", *module.split(".")).with_suffix(".py")


class NodeErrorCatalogueTests(unittest.TestCase):
    def test_join_body_refusal_is_descriptive_and_preserves_earlier_run_uncertainty(
        self,
    ):
        catalogue = json.loads(
            (ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        entry = catalogue["invalid_join_body"]
        self.assertIn("before dispatching this request", entry["description"])
        self.assertIn("does not stop earlier work", entry["recovery"])
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/interface/langflow/component.py").read_text(
                encoding="utf-8"
            )
        )
        routed = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_ROUTABLE_ERRORS"
                for target in node.targets
            )
        )
        self.assertIn("invalid_join_body", routed)

    def test_opencode_discovery_recovery_names_the_existing_user_controls(self):
        catalogue = json.loads(
            (ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        recovery = catalogue["opencode_model_discovery_in_progress"]["recovery"]
        self.assertNotIn("operator", recovery.lower())
        self.assertIn("Provider/Model", recovery)
        self.assertIn("Refresh list", recovery)
        self.assertIn("did not start an agent task", recovery)

    def test_reworked_working_state_and_git_producers_are_catalogued_and_routable(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        component = ast.parse(
            (ROOT / "src/laomedo/agents/interface/langflow/component.py").read_text()
        )
        routed = next(
            ast.literal_eval(n.value)
            for n in component.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_ROUTABLE_ERRORS"
                for t in n.targets
            )
        )
        paths = (
            "agents/workspaces/workspace.py",
            "agents/workspaces/utils.py",
            "skills/workspace/utils.py",
            "git/worktree.py",
            "host/mediation/agent_cli.py",
        )
        codes = {"git_timeout", "git_timeout_cleanup_unverified"}
        for relative in paths:
            tree = ast.parse((ROOT / "src/laomedo" / relative).read_text())
            codes.update(
                n.exc.args[0].value
                for n in ast.walk(tree)
                if isinstance(n, ast.Raise)
                and isinstance(n.exc, ast.Call)
                and n.exc.args
                and isinstance(n.exc.args[0], ast.Constant)
                and isinstance(n.exc.args[0].value, str)
            )
        self.assertFalse(codes - catalogue.keys())
        self.assertFalse(codes - routed)
        for code in codes:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))

    def test_shared_acp_timeout_methods_are_preserved_by_the_graph_boundary(self):
        source = ast.parse(
            (ROOT / "src/laomedo/agents/agents/base/acp/session.py").read_text()
        )
        methods = {
            node.args[1].value
            for node in ast.walk(source)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_request"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        }
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/interface/langflow/component.py").read_text()
        )
        routed = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_ROUTABLE_ERRORS"
                for target in node.targets
            )
        )
        self.assertTrue(methods)
        self.assertFalse({"request_timeout:" + method for method in methods} - routed)

    def test_opencode_catalogue_codes_survive_the_graph_boundary(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/interface/langflow/component.py").read_text()
        )
        routed = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_ROUTABLE_ERRORS"
                for target in node.targets
            )
        )
        self.assertFalse(
            {code for code in catalogue if code.startswith("opencode_")} - routed
        )

    def test_handoff_selection_producer_has_catalogue_coverage(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        source = ast.parse((ROOT / "components/laomedo/handoff.py").read_text())
        codes = {
            node.exc.args[0].value
            for node in ast.walk(source)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and node.exc.args
            and isinstance(node.exc.args[0], ast.Constant)
            and isinstance(node.exc.args[0].value, str)
        }
        self.assertFalse(codes - catalogue.keys())
        for code in codes:
            for key in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][key].strip())

    def test_catalogue_keys_are_unique(self):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result, f"Duplicate error catalogue key: {key}")
                result[key] = value
            return result

        json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text(),
            object_pairs_hook=unique,
        )

    def test_local_saved_graph_auth_producer_is_catalogued_and_routable(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        source = ast.parse(
            (ROOT / "src/laomedo/work_graph/local_launch.py").read_text()
        )
        codes = {
            node.exc.args[0].value
            for node in ast.walk(source)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and node.exc.args
            and isinstance(node.exc.args[0], ast.Constant)
            and isinstance(node.exc.args[0].value, str)
        }
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/interface/langflow/component.py").read_text()
        )
        routed = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_ROUTABLE_ERRORS"
                for target in node.targets
            )
        )
        self.assertFalse(codes - catalogue.keys())
        self.assertFalse(codes - routed)
        for code in codes:
            for key in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][key].strip())

    def test_catalogued_claude_codes_survive_component_routing(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/interface/langflow/component.py").read_text(
                encoding="utf-8"
            )
        )
        codes = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "_ROUTABLE_ERRORS"
                for target in node.targets
            )
        )
        self.assertFalse(
            {key for key in catalogue if key.startswith("claude_")} - codes
        )
        self.assertIn("container_termination_unverified", codes)

    def test_claude_runner_public_errors_including_named_codes_have_catalogue_entries(
        self,
    ):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/agents/claude/agent.py").read_text(
                encoding="utf-8"
            )
        )
        assignments = {}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.setdefault(target.id, set()).add(node.value.value)
        missing = []
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and getattr(node.exc.func, "id", getattr(node.exc.func, "attr", ""))
                == "RunnerError"
                and node.exc.args
            ):
                continue
            value = node.exc.args[0]
            codes = (
                {value.value}
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
                else (
                    assignments.get(value.id, set())
                    if isinstance(value, ast.Name)
                    else set()
                )
            )
            self.assertTrue(
                codes,
                f"Add explicit catalogue coverage for dynamic Claude runner error at line {node.lineno}",
            )
            missing.extend(code for code in codes if code not in catalogue)
        self.assertEqual(
            missing,
            [],
            "Every Claude runner public error needs a shared explanation and recovery",
        )

    def test_claude_container_and_join_public_codes_have_explanations(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        for filename in (
            "claude_container.py",
            "langflow_join.py",
            "runner_trace_bridge.py",
            "handoff_http.py",
            "agent_activity_capture.py",
            "agent_activity.py",
        ):
            # Catalogue the boundary's public exception types across defining siblings.
            # Claude catalogue parser ValueErrors become RunnerError at _discover_models;
            # join config/parser ValueErrors are private setup or become join_request_refused.
            public_types = {"RunnerError", "LaunchError", "HistoryError"}
            if filename.startswith("agent_activity"):
                public_types.add("ValueError")
            if filename == "handoff_http.py":
                public_types = {"HandoffError"}
            for path in producer_paths(filename):
                # The handoff transport did not split. Controller/envelope validation
                # is a separate pre-existing producer, outside this affected boundary.
                if filename == "handoff_http.py" and path != producer_path(filename):
                    continue
                # Separate bridge HTTP parser and service startup producers did not
                # belong to langflow_join.py; their existing coverage gap is retained.
                if filename == "langflow_join.py" and path.stem in {
                    "server",
                    "service",
                }:
                    continue
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if (
                        isinstance(node, ast.Raise)
                        and isinstance(node.exc, ast.Call)
                        and getattr(
                            node.exc.func, "id", getattr(node.exc.func, "attr", "")
                        )
                        in public_types
                        and node.exc.args
                        and isinstance(node.exc.args[0], ast.Constant)
                    ):
                        code = node.exc.args[0].value
                        self.assertTrue(
                            code in catalogue,
                            f"{path.relative_to(ROOT)}:{node.lineno}: missing {code}",
                        )
                        for key in ("title", "description", "recovery"):
                            self.assertTrue(catalogue[code][key].strip())

    def test_affected_runner_skill_preparation_and_workspace_errors_are_catalogued(
        self,
    ):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        producers = {
            "local_runner.py": {"_prepare", "_materialize"},
            "opencode_runner.py": {"_verify_pinned_skills"},
            "workspace_skills.py": {"verify", "install", "_exclude"},
        }
        missing = []
        for filename, names in producers.items():
            tree = ast.parse(
                "\n".join(path.read_text() for path in producer_paths(filename))
            )
            found = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
            }
            self.assertTrue(names <= found, (filename, names - found))
            for function in ast.walk(tree):
                if (
                    not isinstance(function, ast.FunctionDef)
                    or function.name not in names
                ):
                    continue
                for node in ast.walk(function):
                    if not (
                        isinstance(node, ast.Raise)
                        and isinstance(node.exc, ast.Call)
                        and node.exc.args
                    ):
                        continue
                    value = node.exc.args[0]
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value not in catalogue
                    ):
                        missing.append(f"{filename}:{node.lineno}:{value.value}")
        self.assertEqual(
            missing,
            [],
            "Affected runner skill validation needs shared explanations and recovery",
        )

    def test_normal_attempt_accounting_codes_have_catalogue_coverage(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        source = ast.parse(
            (ROOT / "src/laomedo/agents/agents/base/agent.py").read_text(
                encoding="utf-8"
            )
        )
        method = next(
            node
            for node in ast.walk(source)
            if isinstance(node, ast.FunctionDef) and node.name == "_reserve_turn"
        )
        codes = {
            node.exc.args[0].value
            for node in ast.walk(method)
            if isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and node.exc.args
            and isinstance(node.exc.args[0], ast.Constant)
        }
        self.assertFalse(codes)
        self.assertEqual(codes - catalogue.keys(), set())

    def test_literal_agent_failures_have_descriptive_catalogue_entries(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        missing = []
        for source in [
            *(ROOT / "components/laomedo").glob("*agent.py"),
            ROOT / "components/laomedo/handoff.py",
            ROOT / "components/laomedo/bounded_controller.py",
            ROOT / "src/laomedo/agents/interface/langflow/component.py",
        ]:
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if (
                    not isinstance(node, ast.Raise)
                    or not isinstance(node.exc, ast.Call)
                    or not node.exc.args
                ):
                    continue
                argument = node.exc.args[0]
                if not isinstance(argument, ast.Constant) or not isinstance(
                    argument.value, str
                ):
                    continue
                code = argument.value
                if code and all(
                    character.islower() or character.isdigit() or character == "_"
                    for character in code
                ):
                    if code not in catalogue:
                        missing.append(f"{source.name}:{node.lineno}: {code}")
        self.assertEqual(
            missing,
            [],
            "Add a user explanation for each new literal Agent failure code",
        )

    def test_claude_literal_failures_are_covered_when_provider_is_installed(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        sources = [
            path
            for name in (
                "claude_runner.py",
                "claude_container.py",
                "claude_telemetry.py",
            )
            for path in producer_paths(name)
        ]
        sources = [path for path in sources if path.exists()]
        if not sources:
            self.skipTest(
                "Claude producer belongs to the pending provider PR, not this tree"
            )
        codes = set()
        for path in sources:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if (
                    isinstance(node, ast.Raise)
                    and isinstance(node.exc, ast.Call)
                    and node.exc.args
                ):
                    value = node.exc.args[0]
                    if (
                        isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                        and value.value.startswith("claude_")
                    ):
                        codes.add(value.value)
        self.assertEqual(
            codes - catalogue.keys(),
            set(),
            "Catalogue every installed literal Claude failure",
        )

    def test_claude_stored_capture_codes_are_catalogued(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        codes = set()
        for name in ("claude_runner.py", "claude_telemetry.py"):
            codes.update(
                code
                for path in producer_paths(name)
                for code in emitted_codes(path.read_text(encoding="utf-8"))
                if code.startswith("claude_")
            )
        self.assertIn("claude_telemetry_capture_failed", codes)
        self.assertIn("claude_telemetry_cleanup_unconfirmed", codes)
        self.assertFalse(codes - catalogue.keys())

    def test_runner_service_public_codes_have_catalogue_coverage(self):
        catalogue = json.loads(
            (
                ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text()
        )
        source = ast.parse((ROOT / "src/laomedo/host/runner/service.py").read_text())
        codes = set()
        for node in ast.walk(source):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in {
                        "reason",
                        "code",
                    }:
                        for literal in ast.walk(value):
                            if isinstance(literal, ast.Constant) and isinstance(
                                literal.value, str
                            ):
                                codes.add(literal.value)
        self.assertTrue(codes)
        self.assertEqual(codes - catalogue.keys(), set())


OPENCODE_ERROR_PRODUCERS = tuple(
    sorted(
        {"components/laomedo/opencode_agent.py"}
        | {
            path.relative_to(ROOT).as_posix()
            for name in (
                "opencode_runner.py",
                "opencode_boundary.py",
                "opencode_telemetry.py",
                "agent_activity_capture.py",
            )
            for path in producer_paths(name)
        }
        | {
            path.relative_to(ROOT).as_posix()
            for folder in (
                "src/laomedo/agents/agents/opencode",
                "src/laomedo/agents/agents/base/acp",
                "src/laomedo/agents/activity/acp",
            )
            for path in ROOT.joinpath(folder).rglob("*.py")
        }
    )
)

_ERROR_FIELDS = {"error", "error_category", "capture_error", "reason"}


def emitted_codes(source):
    """Inspect public literals, not every underscore-containing data-field name.

    Dynamic external failures use the presenter's safe fallback; they are not
    assumed covered by this literal guard.
    """
    tree = ast.parse(source)
    candidates = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and node.exc.args
        ):
            candidates.append(node.exc.args[0])
        if isinstance(node, ast.Call):
            candidates.extend(
                keyword.value
                for keyword in node.keywords
                if keyword.arg in _ERROR_FIELDS
            )
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "setdefault"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value in _ERROR_FIELDS
            ):
                candidates.append(node.args[1])
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in _ERROR_FIELDS:
                    candidates.append(node.value)
                elif (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value in _ERROR_FIELDS
                ):
                    candidates.append(node.value)
        if isinstance(node, ast.Dict):
            candidates.extend(
                value
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and key.value in _ERROR_FIELDS
            )

    def literals(node):
        if isinstance(node, ast.Constant):
            yield node.value
        elif isinstance(node, ast.IfExp):
            yield from literals(node.body)
            yield from literals(node.orelse)
        elif isinstance(node, ast.BoolOp):
            for value in node.values:
                yield from literals(value)

    return {
        value
        for candidate in candidates
        for value in literals(candidate)
        if isinstance(value, str)
        and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", value)
    }


class OpenCodeErrorCatalogueTests(unittest.TestCase):
    def test_opencode_runner_boundary_and_capture_codes_have_explanations(self):
        catalog = json.loads(
            (ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        missing = {
            path: sorted(
                emitted_codes((ROOT / path).read_text(encoding="utf-8"))
                - catalog.keys()
            )
            for path in OPENCODE_ERROR_PRODUCERS
        }
        self.assertEqual({path: codes for path, codes in missing.items() if codes}, {})

    def test_changed_normal_accounting_methods_have_catalogue_coverage(self):
        catalog = json.loads(
            (ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text(
                encoding="utf-8"
            )
        )
        tree = ast.parse(
            (ROOT / "src/laomedo/agents/agents/base/agent.py").read_text(
                encoding="utf-8"
            )
        )
        runner = next(
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "BaseAgent"
        )
        methods = {
            node.name: node
            for node in runner.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_reserve_turn", "_turn_available"}
        }
        self.assertEqual(set(methods), {"_reserve_turn", "_turn_available"})
        for name, node in methods.items():
            self.assertEqual(
                emitted_codes(ast.unparse(node)) - catalog.keys(), set(), name
            )

    def test_guard_catches_new_literal_and_nested_capture_failures(self):
        self.assertEqual(
            emitted_codes(
                'raise RuntimeError("new_public_failure")\nself.error="new_capture_failure"\nx.update(capture_error="new_snapshot_failure" if flag else "new_stream_failure")'
            ),
            {
                "new_public_failure",
                "new_capture_failure",
                "new_snapshot_failure",
                "new_stream_failure",
            },
        )

    def test_guard_catches_positional_capture_defaults_and_dictionary_updates(self):
        source = """
x.setdefault("capture_error", capture.error or "new_terminal_failure")
x.setdefault("reason", "new_telemetry_failure")
x.update({"capture_error": "new_dictionary_failure"})
x.update(error_category="new_keyword_failure")
x.setdefault("ordinary_field", "not_an_error")
"""
        self.assertEqual(
            emitted_codes(source),
            {
                "new_terminal_failure",
                "new_telemetry_failure",
                "new_dictionary_failure",
                "new_keyword_failure",
            },
        )


if __name__ == "__main__":
    unittest.main()
