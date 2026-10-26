"""Cover Agent errors and the affected runner skill-validation producers."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NodeErrorCatalogueTests(unittest.TestCase):
    def test_catalogued_claude_codes_survive_component_routing(self):
        catalogue=json.loads((ROOT/'frontend/langflow-skill-viewer/node-error-catalog.json').read_text())
        tree=ast.parse((ROOT/'components/laomedo/codex_agent.py').read_text(encoding='utf-8'))
        codes=next(ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
                   and any(isinstance(target,ast.Name) and target.id=='_ROUTABLE_ERRORS' for target in node.targets))
        self.assertFalse({key for key in catalogue if key.startswith('claude_')}-codes)
        self.assertIn('container_termination_unverified',codes)
    def test_claude_runner_public_errors_including_named_codes_have_catalogue_entries(self):
        catalogue=json.loads((ROOT/'frontend/langflow-skill-viewer/node-error-catalog.json').read_text())
        tree=ast.parse((ROOT/'laomedo/claude_runner.py').read_text(encoding='utf-8'))
        assignments={}
        for node in ast.walk(tree):
            if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
                for target in node.targets:
                    if isinstance(target,ast.Name):assignments.setdefault(target.id,set()).add(node.value.value)
        missing=[]
        for node in ast.walk(tree):
            if not (isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call)
                    and isinstance(node.exc.func,ast.Name) and node.exc.func.id=='RunnerError' and node.exc.args):continue
            value=node.exc.args[0]
            codes={value.value} if isinstance(value,ast.Constant) and isinstance(value.value,str) else assignments.get(value.id,set()) if isinstance(value,ast.Name) else set()
            self.assertTrue(codes,f'Add explicit catalogue coverage for dynamic Claude runner error at line {node.lineno}')
            missing.extend(code for code in codes if code not in catalogue)
        self.assertEqual(missing,[],'Every Claude runner public error needs a shared explanation and recovery')

    def test_claude_container_and_join_public_codes_have_explanations(self):
        catalogue=json.loads((ROOT/'frontend/langflow-skill-viewer/node-error-catalog.json').read_text())
        for filename in ('claude_container.py', 'langflow_join.py', 'runner_trace_bridge.py', 'handoff_http.py', 'agent_activity_capture.py', 'agent_activity.py'):
            tree=ast.parse((ROOT/'laomedo'/filename).read_text())
            for node in ast.walk(tree):
                if (isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call) and
                    isinstance(node.exc.func,ast.Name) and node.exc.func.id in {'RunnerError','LaunchError','HandoffError','ValueError'} and
                    node.exc.args and isinstance(node.exc.args[0],ast.Constant)):
                    code=node.exc.args[0].value
                    self.assertIn(code,catalogue,f'{filename}:{node.lineno}: missing {code}')
                    for key in ('title','description','recovery'):
                        self.assertTrue(catalogue[code][key].strip())

    def test_affected_runner_skill_preparation_and_workspace_errors_are_catalogued(self):
        catalogue=json.loads((ROOT/'frontend/langflow-skill-viewer/node-error-catalog.json').read_text())
        producers={'local_runner.py':{'_prepare','_materialize'},
                   'opencode_runner.py':{'_verify_pinned_skills'},
                   'workspace_skills.py':{'verify','install','_exclude'}}
        missing=[]
        for filename,names in producers.items():
            tree=ast.parse((ROOT/'laomedo'/filename).read_text())
            for function in ast.walk(tree):
                if not isinstance(function,ast.FunctionDef) or function.name not in names:continue
                for node in ast.walk(function):
                    if not (isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call) and node.exc.args):continue
                    value=node.exc.args[0]
                    if isinstance(value,ast.Constant) and isinstance(value.value,str) and value.value not in catalogue:
                        missing.append(f'{filename}:{node.lineno}:{value.value}')
        self.assertEqual(missing,[],'Affected runner skill validation needs shared explanations and recovery')
    def test_normal_attempt_accounting_codes_have_catalogue_coverage(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        source = ast.parse((ROOT / "laomedo/local_runner.py").read_text(encoding="utf-8"))
        method = next(node for node in ast.walk(source)
                      if isinstance(node, ast.FunctionDef) and node.name == "_reserve_turn")
        codes = {node.exc.args[0].value for node in ast.walk(method)
                 if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call)
                 and node.exc.args and isinstance(node.exc.args[0], ast.Constant)}
        self.assertFalse(codes)
        self.assertEqual(codes - catalogue.keys(), set())

    def test_literal_agent_failures_have_descriptive_catalogue_entries(self):
        catalogue = json.loads((ROOT / "frontend/langflow-skill-viewer/node-error-catalog.json").read_text())
        missing = []
        for source in [*(ROOT / "components/laomedo").glob("*agent.py"), ROOT/"components/laomedo/handoff.py", ROOT/"components/laomedo/bounded_controller.py"]:
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


if __name__ == "__main__":
    unittest.main()
