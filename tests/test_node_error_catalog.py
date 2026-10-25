"""Prevent newly emitted Agent codes from silently losing their user explanation."""
import ast
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NodeErrorCatalogueTests(unittest.TestCase):
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

    def test_guard_catches_new_literal_and_nested_capture_failures(self):
        self.assertEqual(emitted_codes('raise RuntimeError("new_public_failure")\nself.error="new_capture_failure"\nx.update(capture_error="new_snapshot_failure" if flag else "new_stream_failure")'),
                         {"new_public_failure","new_capture_failure","new_snapshot_failure","new_stream_failure"})


if __name__ == "__main__":
    unittest.main()
