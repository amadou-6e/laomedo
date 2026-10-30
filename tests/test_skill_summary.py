from pathlib import Path
import tempfile
import unittest

from laomedo.skills.authoring.summary import has_description
from laomedo.skills.authoring.summary import summary_authoring
from laomedo.skills.registry.store import SkillStore
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.operations.service import SkillOperations


class SkillSummaryTests(unittest.TestCase):
    def test_unreadable_skill_fails_before_authoring(self):
        with self.assertRaisesRegex(
            SkillStoreError, "skill_summary_source_unavailable"
        ):
            summary_authoring({"files": [{"path": "SKILL.md", "text": None}]})

    def test_missing_and_user_authored_yaml_descriptions(self):
        for value in ["", " # not a value", "null", "~", '""', "''", ">\n  ", "|-\n  "]:
            self.assertFalse(
                has_description(
                    "---\nname: unit\ndescription: " + value + "\n---\nBody"
                ),
                value,
            )
        for value in [
            "User summary.",
            '"null"',
            "\n  User-written multiline summary.",
            "|-\n  # Literal summary content",
            ">\n  User summary.",
            '"User # words"',
            "Acronym e.g. remains intact.",
        ]:
            self.assertTrue(
                has_description(
                    "\ufeff---\r\nname: unit\r\ndescription: " + value + "\n---\nBody"
                ),
                value,
            )

    def test_preparation_loads_internal_skill_and_apply_records_traceable_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            original = "---\nname: summary-unit\n---\n# Internal unit fixture\nExplain the selected revision.\n"
            (source / "SKILL.md").write_text(original, encoding="utf-8")
            store = SkillStore(root / "registry")
            initial = store.import_skill("summary-unit", source)
            policy = {
                "policy_id": "summary-unit",
                "revision_id": "1",
                "allowed_paths": ["SKILL.md"],
                "allowed_suffixes": [".md"],
                "allow_new_files": False,
                "allow_deletions": False,
                "allow_scripts": False,
                "allow_dependencies": False,
                "allow_assets": False,
                "required_frontmatter": ["name"],
                "permitted_validation_commands": [],
                "max_files": 1,
                "max_file_bytes": 8192,
            }
            service = SkillOperations(
                store, root / "history.db", {"summary-unit": policy}
            )
            prepared = service.prepare("summary-unit", initial["revision_id"])
            self.assertTrue(prepared["summary_required"])
            self.assertIn(
                "Return exactly one Skill Operation JSON object",
                prepared["authoring_instructions"],
            )
            self.assertNotIn("---", prepared["authoring_instructions"])
            self.assertNotIn("## Host integration", prepared["authoring_instructions"])
            self.assertNotIn(
                "records the accepted immutable revision",
                prepared["authoring_instructions"],
            )
            with self.assertRaisesRegex(SkillStoreError, "skill_summary_required"):
                service.apply(
                    prepared["ticket"],
                    {
                        "action": "modify",
                        "message": "No summary",
                        "files": [
                            {
                                "path": "SKILL.md",
                                "content": original + "More instructions.\n",
                            }
                        ],
                    },
                )
            revised = original.replace(
                "name: summary-unit\n",
                "name: summary-unit\ndescription: Explain selected revisions.\n",
            )
            result = service.apply(
                prepared["ticket"],
                {
                    "action": "modify",
                    "message": "Add missing summary",
                    "files": [{"path": "SKILL.md", "content": revised}],
                },
            )
            self.assertEqual(result["commit"]["parent_commit"], prepared["base_commit"])
            self.assertIn(
                "+description: Explain selected revisions.", result["commit"]["patch"]
            )
            self.assertEqual(
                store.revision("summary-unit")["revision_id"], initial["revision_id"]
            )
            next_task = service.prepare(
                "summary-unit",
                result["skill"]["revision_id"],
                result["commit"]["commit_id"],
            )
            self.assertFalse(next_task["summary_required"])
            self.assertEqual(next_task["authoring_instructions"], "")
            with self.assertRaisesRegex(SkillStoreError, "skill_summary_required"):
                service.apply(
                    next_task["ticket"],
                    {
                        "action": "modify",
                        "message": "Remove existing summary",
                        "files": [{"path": "SKILL.md", "content": original}],
                    },
                )


if __name__ == "__main__":
    unittest.main()
