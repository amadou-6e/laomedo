"""Native Claude commands require live advertisement and root completion evidence."""

import unittest

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.claude.commands import ClaudeCommands
from laomedo.agents.errors import RunnerError


class ClaudeCommandTests(unittest.TestCase):
    """Exercise the supported contract without a model or synthetic CLI answers."""

    def test_admission_binds_catalog_handler_and_builtin_provenance(self):
        catalog = NativeCommandCatalog(
            commands=[{"name": "compact", "description": "Compact context"}]
        )
        image = "sha256:" + "a" * 64
        projected = ClaudeCommands.project(
            catalog.model_dump(), image, builtins_only=True
        )
        command = NativeCommandInvocation(
            name="compact", catalog_revision=projected["revision"]
        )
        ClaudeCommands.admit(command, catalog, image, builtins_only=True)
        for changed, builtin in (("sha256:" + "b" * 64, True), (image, False)):
            with self.assertRaises(RunnerError):
                ClaudeCommands.admit(command, catalog, changed, builtins_only=builtin)
        self.assertFalse(
            ClaudeCommands.project(catalog.model_dump(), image, builtins_only=False)[
                "commands"
            ][0]["executable"]
        )
        with self.assertRaises(RunnerError):
            ClaudeCommands.validate(
                command.model_copy(update={"arguments": "instructions"})
            )

    def test_only_root_native_compaction_evidence_establishes_completion(self):
        event = {
            "type": "system",
            "subtype": "compact_boundary",
            "uuid": "receipt",
            "session_id": "root",
        }
        result = ClaudeCommands.result([event], "root", "end_turn")
        self.assertEqual(result.native_terminal["event_id"], "receipt")
        self.assertNotIn("answer", result.model_dump())
        for events, stop in (
            ([], "end_turn"),
            ([{**event, "session_id": "other"}], "end_turn"),
            ([{**event, "parent_tool_use_id": "child"}], "end_turn"),
            ([event], "cancelled"),
            (
                [
                    event,
                    {
                        "type": "system",
                        "session_id": "root",
                        "compact_result": "failed",
                    },
                ],
                "end_turn",
            ),
        ):
            with self.subTest(events=events, stop=stop), self.assertRaises(RunnerError):
                ClaudeCommands.result(events, "root", stop)

    def test_status_success_requires_a_prior_native_start(self):
        start = {"type": "system", "session_id": "root", "status": "compacting"}
        end = {
            "type": "system",
            "session_id": "root",
            "uuid": "receipt",
            "compact_result": "success",
        }
        with self.assertRaises(RunnerError):
            ClaudeCommands.result([end], "root", "end_turn")
        self.assertEqual(
            ClaudeCommands.result([start, end], "root", "end_turn").command, "compact"
        )
