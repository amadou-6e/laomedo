"""System-skill admission tests; no native process or model is used."""

import unittest

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.codex.commands import CodexCommands
from laomedo.agents.errors import RunnerError


class BundledSkillTests(unittest.TestCase):
    """Only an unambiguous native system source can reach supported invocation."""

    def test_currency_is_text_but_native_plain_and_linked_mentions_require_approval(
        self,
    ):
        CodexCommands.validate_skill_mentions("$20 a month — is that the price?")
        for text in (
            "Explain $skill-creator",
            "Use $imagegen",
            r"Explain \$skill-creator",
            "[$other](skill:///home/runner/.codex/skills/.system/skill-installer/SKILL.md)",
        ):
            with self.subTest(text=text), self.assertRaises(RunnerError):
                CodexCommands.validate_skill_mentions(text)
        command = NativeCommandInvocation(
            name="$skill-creator", catalog_revision="a" * 64
        )
        CodexCommands.validate_skill_mentions("$skill-creator Explain", command)
        with self.assertRaises(RunnerError):
            CodexCommands.validate_skill_mentions(
                "$skill-creator Use $imagegen", command
            )

    def test_skill_success_requires_an_ordered_attempt_and_native_turn_bound_receipt(
        self,
    ):
        invocation = "00000000-0000-4000-8000-000000000001"
        command = NativeCommandInvocation(
            name="$skill-creator", catalog_revision="a" * 64
        )
        events = [
            {
                "method": "turn/started",
                "params": {"threadId": "thread", "turn": {"id": "turn"}},
            },
            {
                "method": "laomedo/skillInput",
                "params": {
                    "threadId": "thread",
                    "turnId": "turn",
                    "invocationId": invocation,
                    "origin": "laomedo_adapter",
                    "phase": "native_turn_accepted",
                    "name": "skill-creator",
                    "path": "/home/runner/.codex/skills/.system/skill-creator/SKILL.md",
                    "manifestSha256": "a" * 64,
                },
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread",
                    "turn": {"id": "turn", "status": "completed"},
                },
            },
        ]
        receipt = CodexCommands.skill_receipt(
            events,
            command,
            session_id="thread",
            turn_id="turn",
            invocation_id=invocation,
        )
        self.assertEqual(receipt.name, "skill-creator")
        for changed in (
            events[:1] + events[2:],
            list(reversed(events)),
            [*events, events[1]],
        ):
            with self.assertRaises(RunnerError):
                CodexCommands.skill_receipt(
                    changed,
                    command,
                    session_id="thread",
                    turn_id="turn",
                    invocation_id=invocation,
                )
        with self.assertRaises(RunnerError):
            CodexCommands.skill_receipt(
                events,
                command,
                session_id="thread",
                turn_id="other",
                invocation_id=invocation,
            )
        with self.assertRaises(RunnerError):
            CodexCommands.skill_receipt(
                events,
                command,
                session_id="thread",
                turn_id="turn",
                invocation_id="00000000-0000-4000-8000-000000000002",
            )

    def catalog(self, skill_name="skill-creator", **source):
        return NativeCommandCatalog.model_validate(
            {
                "commands": [
                    {
                        "name": "$" + skill_name,
                        "description": "Create a skill",
                        "_meta": {
                            "laomedo": {
                                "skill": {
                                    "name": skill_name,
                                    "scope": "system",
                                    "enabled": True,
                                    "path": "/home/runner/.codex/skills/.system/"
                                    + skill_name
                                    + "/SKILL.md",
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

    def test_docs_skill_uses_the_same_verified_model_turn_admission(self):
        catalog = self.catalog("openai-docs")
        row = CodexCommands.project(catalog.model_dump())["commands"][0]
        self.assertTrue(row["executable"])
        self.assertTrue(row["may_use_model"])
        command = NativeCommandInvocation(
            name="$openai-docs",
            arguments="Explain Responses API",
            catalog_revision=catalog.revision(),
        )
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
