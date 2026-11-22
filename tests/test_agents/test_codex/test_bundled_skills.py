"""System-skill admission tests; no native process or model is used."""

import unittest

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.codex.commands import CodexCommands
from laomedo.agents.errors import RunnerError


class BundledSkillTests(unittest.TestCase):
    """Only an unambiguous native system source can reach supported invocation."""

    def catalog(self, **source):
        return NativeCommandCatalog.model_validate(
            {
                "commands": [
                    {
                        "name": "$skill-creator",
                        "description": "Create a skill",
                        "_meta": {
                            "laomedo": {
                                "skill": {
                                    "name": "skill-creator",
                                    "scope": "system",
                                    "enabled": True,
                                    "path": "/home/runner/.codex/skills/.system/skill-creator/SKILL.md",
                                    **source,
                                }
                            }
                        },
                    }
                ]
            }
        )

    def test_system_skill_is_a_model_turn_with_native_dollar_syntax(self):
        catalog = self.catalog()
        row = CodexCommands.project(catalog.model_dump())["commands"][0]
        self.assertEqual(row["kind"], "skill")
        self.assertTrue(row["executable"])
        self.assertTrue(row["may_use_model"])
        command = NativeCommandInvocation(
            name="$skill-creator",
            arguments="Explain the workflow",
            catalog_revision=catalog.revision(),
        )
        self.assertEqual(command.text(), "$skill-creator Explain the workflow")
        self.assertEqual(CodexCommands.admit(command, catalog), "turn")

    def test_user_disabled_changed_or_ambiguous_sources_are_refused(self):
        for source in (
            {"scope": "user"},
            {"enabled": False},
            {"path": "/draft/SKILL.md"},
        ):
            with self.subTest(source=source):
                catalog = self.catalog(**source)
                row = CodexCommands.project(catalog.model_dump())["commands"][0]
                self.assertFalse(row["executable"])
                with self.assertRaises(RunnerError):
                    CodexCommands.admit(
                        NativeCommandInvocation(
                            name="$skill-creator", catalog_revision=catalog.revision()
                        ),
                        catalog,
                    )
        catalog = self.catalog()
        duplicate = NativeCommandCatalog(commands=catalog.commands * 2)
        self.assertFalse(
            CodexCommands.project(duplicate.model_dump())["commands"][0]["executable"]
        )
        changed = self.catalog(scope="user")
        with self.assertRaises(RunnerError):
            CodexCommands.admit(
                NativeCommandInvocation(
                    name="$skill-creator", catalog_revision=catalog.revision()
                ),
                changed,
            )
