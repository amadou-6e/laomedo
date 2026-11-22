"""Native Claude commands require live advertisement and root completion evidence."""

import unittest

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.claude.commands import ClaudeCommands
from laomedo.agents.agents.claude.models import ClaudeControlResult
from laomedo.agents.errors import RunnerError


class ClaudeCommandTests(unittest.TestCase):
    """Supporting receipt-validation tests, never live native acceptance."""

    def test_read_only_views_require_advertisement_and_no_arguments(self):
        for name in ("usage", "context", "mcp"):
            with self.subTest(name=name):
                catalog = NativeCommandCatalog(
                    commands=[{"name": name, "description": "Native view"}]
                )
                image = "sha256:" + "a" * 64
                projection = ClaudeCommands.project(
                    catalog.model_dump(), image, builtins_only=True
                )
                self.assertTrue(projection["commands"][0]["executable"])
                self.assertFalse(projection["commands"][0]["may_use_model"])
                command = NativeCommandInvocation(
                    name=name, catalog_revision=projection["revision"]
                )
                ClaudeCommands.admit(command, catalog, image, builtins_only=True)
                with self.assertRaises(RunnerError):
                    ClaudeCommands.validate(
                        command.model_copy(update={"arguments": "reconnect all"})
                    )
                with self.assertRaises(RunnerError):
                    ClaudeCommands.admit(
                        command,
                        NativeCommandCatalog(commands=[]),
                        image,
                        builtins_only=True,
                    )

    def test_read_only_views_retain_actual_text_and_native_control_identity(self):
        event = {
            "type": "system",
            "subtype": "local_command_output",
            "session_id": "root",
            "uuid": "native-receipt",
        }
        for name in ("usage", "context", "mcp"):
            with self.subTest(name=name):
                result = ClaudeCommands.result(
                    [
                        event,
                        {
                            "type": "result",
                            "session_id": "root",
                            "subtype": "success",
                            "usage": {"output_tokens": 0},
                        },
                    ],
                    "root",
                    "end_turn",
                    command=name,
                    answer="Actual ACP output",
                )
                self.assertIsInstance(result, ClaudeControlResult)
                self.assertEqual(result.command, name)
                self.assertEqual(result.answer, "Actual ACP output")
                self.assertEqual(result.native_terminal["kind"], "local_command_output")
                self.assertNotIn("usage", result.model_dump())

    def test_native_local_run_requires_matching_command_and_zero_output_result(self):
        local = {
            "type": "assistant",
            "session_id": "root",
            "uuid": "native-local-output",
            "local_command_run": {"command": "usage", "args": ""},
        }
        result = {
            "type": "result",
            "session_id": "root",
            "subtype": "success",
            "usage": {"output_tokens": 0},
            "local_command": "usage",
        }
        value = ClaudeCommands.result(
            [local, result],
            "root",
            "end_turn",
            command="usage",
            answer="Native usage view",
        )
        self.assertEqual(value.native_terminal["kind"], "local_command_run")
        for events in (
            [local],
            [result],
            [
                {**local, "local_command_run": {"command": "context", "args": ""}},
                result,
            ],
            [
                {
                    **local,
                    "local_command_run": {"command": "usage", "args": "unexpected"},
                },
                result,
            ],
            [local, {**result, "local_command": "context"}],
            [local, {**result, "usage": {"output_tokens": 1}}],
            [{**local, "parent_tool_use_id": "child"}, result],
        ):
            with self.subTest(events=events), self.assertRaises(RunnerError):
                ClaudeCommands.result(
                    events,
                    "root",
                    "end_turn",
                    command="usage",
                    answer="Native usage view",
                )

    def test_control_completion_refuses_missing_foreign_failed_or_model_receipts(self):
        event = {
            "type": "system",
            "subtype": "local_command_output",
            "session_id": "root",
            "uuid": "native-receipt",
        }
        for events, stop, answer in (
            ([], "end_turn", "Output"),
            ([event], "end_turn", "Output"),
            ([{**event, "session_id": "other"}], "end_turn", "Output"),
            ([{**event, "parent_tool_use_id": "child"}], "end_turn", "Output"),
            ([{**event, "uuid": None}], "end_turn", "Output"),
            ([event], "cancelled", "Output"),
            ([event], "end_turn", ""),
            ([event], "end_turn", "x" * 1048577),
            (
                [
                    event,
                    {
                        "type": "result",
                        "session_id": "root",
                        "subtype": "success",
                        "usage": {"output_tokens": 1},
                    },
                ],
                "end_turn",
                "Output",
            ),
            (
                [
                    event,
                    {
                        "type": "result",
                        "session_id": "root",
                        "subtype": "success",
                        "usage": [],
                    },
                ],
                "end_turn",
                "Output",
            ),
            (
                [
                    event,
                    {
                        "type": "result",
                        "session_id": "root",
                        "subtype": "error_during_execution",
                        "is_error": True,
                    },
                ],
                "end_turn",
                "Output",
            ),
        ):
            with self.subTest(events=events, stop=stop), self.assertRaises(RunnerError):
                ClaudeCommands.result(
                    events, "root", stop, command="usage", answer=answer
                )

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
