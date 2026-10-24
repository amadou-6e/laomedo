"""Cover Agent errors and the affected runner skill-validation producers."""
import ast
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NodeErrorCatalogueTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
