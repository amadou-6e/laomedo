"""Prevent newly emitted Agent codes from silently losing their user explanation."""
import ast
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NodeErrorCatalogueTests(unittest.TestCase):
    def test_normal_attempt_accounting_codes_have_catalogue_coverage(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        source = ast.parse((ROOT / "laomedo/local_runner.py").read_text(encoding="utf-8"))
        method = next(node for node in ast.walk(source)
                      if isinstance(node, ast.FunctionDef) and node.name == "_reserve_turn")
        codes = {node.exc.args[0].value for node in ast.walk(method)
                 if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                 and node.exc.args and isinstance(node.exc.args[0], ast.Constant)}
        self.assertTrue(codes)
        self.assertEqual(codes - catalogue.keys(), set())

    def test_literal_agent_failures_have_descriptive_catalogue_entries(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        missing = []
        for source in (ROOT / "components/laomedo").glob("*agent.py"):
            for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                    continue
                argument = node.exc.args[0]
                if not isinstance(argument, ast.Constant) or not isinstance(argument.value, str):
                    continue
                code = argument.value
                if code and all(character.islower() or character.isdigit() or character == "_" for character in code):
                    if code not in catalogue:
                        missing.append(f"{source.name}:{node.lineno}: {code}")
        self.assertEqual(missing, [], "Add a user explanation for each new literal Agent failure code")

    def test_claude_literal_failures_are_covered_when_provider_is_installed(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        sources = [ROOT / "laomedo" / name for name in ("claude_runner.py", "claude_container.py")]
        sources = [path for path in sources if path.exists()]
        if not sources:
            self.skipTest("Claude producer belongs to the pending provider PR, not this tree")
        codes = set()
        for path in sources:
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                    value = node.exc.args[0]
                    if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith("claude_"):
                        codes.add(value.value)
        self.assertEqual(codes - catalogue.keys(), set(), "Catalogue every installed literal Claude failure")

    def test_runner_service_public_codes_have_catalogue_coverage(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        source = ast.parse((ROOT / "laomedo/runner_service.py").read_text())
        codes = set()
        for node in ast.walk(source):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value in {"reason", "code"}:
                        for literal in ast.walk(value):
                            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                                codes.add(literal.value)
        self.assertTrue(codes)
        self.assertEqual(codes - catalogue.keys(), set())




OPENCODE_ERROR_PRODUCERS = (
    "components/laomedo/opencode_agent.py", "laomedo/opencode_runner.py",
    "laomedo/opencode_boundary.py", "laomedo/opencode_events.py",
    "laomedo/opencode_telemetry.py", "laomedo/agent_activity_capture.py",
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
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
            candidates.append(node.exc.args[0])
        if isinstance(node, ast.Call):
            candidates.extend(keyword.value for keyword in node.keywords if keyword.arg in _ERROR_FIELDS)
            if (isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault"
                    and len(node.args) >= 2 and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value in _ERROR_FIELDS):
                candidates.append(node.args[1])
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and target.attr in _ERROR_FIELDS:
                    candidates.append(node.value)
                elif isinstance(target, ast.Subscript) and isinstance(target.slice, ast.Constant) and target.slice.value in _ERROR_FIELDS:
                    candidates.append(node.value)
        if isinstance(node, ast.Dict):
            candidates.extend(value for key,value in zip(node.keys,node.values) if isinstance(key,ast.Constant) and key.value in _ERROR_FIELDS)
    def literals(node):
        if isinstance(node,ast.Constant):
            yield node.value
        elif isinstance(node,ast.IfExp):
            yield from literals(node.body)
            yield from literals(node.orelse)
        elif isinstance(node,ast.BoolOp):
            for value in node.values:
                yield from literals(value)
    return {value for candidate in candidates for value in literals(candidate)
            if isinstance(value,str) and re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+",value)}

class OpenCodeErrorCatalogueTests(unittest.TestCase):
    def test_opencode_runner_boundary_and_capture_codes_have_explanations(self):
        catalog=json.loads((ROOT/"frontend/langflow-skill-viewer/node-error-catalog.json").read_text(encoding="utf-8"))
        missing={path:sorted(emitted_codes((ROOT/path).read_text(encoding="utf-8"))-catalog.keys()) for path in OPENCODE_ERROR_PRODUCERS}
        self.assertEqual({path:codes for path,codes in missing.items() if codes},{})

    def test_changed_normal_accounting_methods_have_catalogue_coverage(self):
        catalog=json.loads((ROOT/"frontend/langflow-skill-viewer/node-error-catalog.json").read_text(encoding="utf-8"))
        tree=ast.parse((ROOT/"laomedo/local_runner.py").read_text(encoding="utf-8"))
        runner=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=="LocalRunner")
        methods={node.name:node for node in runner.body if isinstance(node,ast.FunctionDef) and node.name in {"_reserve_turn","_turn_available"}}
        self.assertEqual(set(methods),{"_reserve_turn","_turn_available"})
        for name,node in methods.items():
            self.assertEqual(emitted_codes(ast.unparse(node))-catalog.keys(),set(),name)

    def test_guard_catches_new_literal_and_nested_capture_failures(self):
        self.assertEqual(emitted_codes('raise RuntimeError("new_public_failure")\nself.error="new_capture_failure"\nx.update(capture_error="new_snapshot_failure" if flag else "new_stream_failure")'),
                         {"new_public_failure","new_capture_failure","new_snapshot_failure","new_stream_failure"})

    def test_guard_catches_positional_capture_defaults_and_dictionary_updates(self):
        source = '''
x.setdefault("capture_error", capture.error or "new_terminal_failure")
x.setdefault("reason", "new_telemetry_failure")
x.update({"capture_error": "new_dictionary_failure"})
x.update(error_category="new_keyword_failure")
x.setdefault("ordinary_field", "not_an_error")
'''
        self.assertEqual(emitted_codes(source), {"new_terminal_failure", "new_telemetry_failure",
                                               "new_dictionary_failure", "new_keyword_failure"})


if __name__ == "__main__":
    unittest.main()
