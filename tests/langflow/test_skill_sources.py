import asyncio
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import importlib.util
import tempfile
import unittest
import sys

from laomedo.skill_sources import SkillSources

ROOT = Path(__file__).resolve().parents[2]


class NativeSkillSourceTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("source_skill_component", ROOT / "components/laomedo/skill.py")
        self.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.module
        spec.loader.exec_module(self.module)
        self.component = self.module.LaomedoSkill()
        self.config = {item.name: item.to_dict() for item in self.component.inputs}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source"
        self.source.mkdir()
        for name in ("alpha", "beta"):
            folder = self.source / name
            folder.mkdir()
            (folder / "SKILL.md").write_text(f"---\nname: {name}\n---\n# {name}")
        self.resolver = SkillSources(root / "registry", root / "state", [self.source])
        def request(action, **body):
            if action == "discover":
                return self.resolver.discover(body["source"])
            if action == "revisions":
                return self.resolver.revisions(body["source"], body["skill"])
            return self.resolver.resolve(body["source"], body["skill"], body["revision"])
        self.stub = patch.object(self.module, "source_request", side_effect=request)
        self.stub.start()
        self.addCleanup(self.stub.stop)

    def update(self, name, value):
        self.config = asyncio.run(self.component.update_build_config(deepcopy(self.config), value, name))

    def test_discovery_selects_and_returns_native_reference(self):
        self.update("source", str(self.source))
        self.assertEqual(self.config["skill_id"]["options"], ["alpha | alpha", "beta | beta"])
        self.assertFalse(self.config["skill_id"]["combobox"])
        self.assertFalse(self.config["revision_id"]["combobox"])
        self.update("skill_id", "alpha | alpha")
        revision = self.config["revision_id"]["options"][0]
        self.update("revision_id", revision)
        self.component.set(source=str(self.source), skill_id="alpha | alpha", revision_id=revision)
        result = self.component.skill_output().data
        self.assertEqual(result["skill_id"], "alpha")
        self.assertEqual(result["revision_id"], self.config["resolved_revision_id"]["value"])
        self.assertEqual(result["tree_hash"], result["revision_id"])

    def test_parent_change_resets_dependencies_and_inspection_provenance(self):
        self.test_discovery_selects_and_returns_native_reference()
        self.update("skill_id", "beta | beta")
        self.assertEqual(self.config["revision_id"]["value"], "")
        self.assertEqual(self.config["resolved_selection"]["value"], "")
        self.update("source", "")
        self.assertEqual(self.config["skill_id"]["value"], "")
        self.assertEqual(self.config["revision_id"]["options"], [])

    def test_failure_and_fabricated_selection_never_fall_back(self):
        self.update("source", str(self.source))
        self.update("skill_id", "invented")
        self.assertEqual(self.config["skill_id"]["value"], "")
        self.assertIn("failed", self.config["discovery_status"]["value"].lower())
        self.component.set(source=str(self.source), skill_id="alpha | alpha", revision_id="made-up")
        with self.assertRaises(ValueError):
            self.component.skill_output()

    def test_existing_manual_pin_remains_compatible(self):
        self.component.set(skill_id="legacy", revision_id="sha256:" + "a" * 64)
        self.assertEqual(self.component.skill_output().data,
                         {"skill_id": "legacy", "revision_id": "sha256:" + "a" * 64, "tree_hash": "sha256:" + "a" * 64})

    def test_refresh_preserves_selected_immutable_revision(self):
        self.update("source", str(self.source))
        self.update("skill_id", "alpha | alpha")
        revision = self.config["revision_id"]["options"][0]
        self.update("revision_id", revision)
        self.update("source", str(self.source))
        self.assertEqual(self.config["skill_id"]["value"], "alpha | alpha")
        self.assertEqual(self.config["revision_id"]["value"], revision)
        self.assertTrue(self.config["resolved_revision_id"]["value"])

    def test_empty_source_status_does_not_keep_discovering_message(self):
        self.config["discovery_status"]["value"] = "Discovering skills..."
        self.update("source", "")
        self.assertEqual(self.config["discovery_status"]["value"], "Supply a source to discover skills.")
