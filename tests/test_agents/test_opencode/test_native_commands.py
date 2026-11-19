"""OpenCode built-ins require pinned admission and successful native child evidence."""

import unittest

from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.opencode.commands import OpenCodeCommands
from laomedo.agents.agents.opencode.history.models import NativeHistory, NativeExport
from laomedo.agents.errors import RunnerError


class OpenCodeCommandTests(unittest.TestCase):
    """No native controller, private profile or model is used by these checks."""

    def test_no_arguments_or_unadvertised_compact_can_be_admitted(self):
        catalog = NativeCommandCatalog(
            commands=[
                {"name": "init", "description": "Initialize"},
                {"name": "review", "description": "Review"},
            ]
        )
        image = "sha256:" + "a" * 64
        projection = OpenCodeCommands.project(
            catalog.model_dump(), image, builtins_only=True
        )
        command = NativeCommandInvocation(
            name="init", catalog_revision=projection["revision"]
        )
        OpenCodeCommands.admit(command, catalog, image, builtins_only=True)
        self.assertNotIn("compact", {item["name"] for item in projection["commands"]})
        for changed in (
            command.model_copy(update={"arguments": "!`id`"}),
            command.model_copy(update={"name": "compact"}),
        ):
            with self.assertRaises(RunnerError):
                OpenCodeCommands.admit(changed, catalog, image, builtins_only=True)
        with self.assertRaises(RunnerError):
            OpenCodeCommands.admit(
                command, catalog, "sha256:" + "b" * 64, builtins_only=True
            )

    def test_review_needs_successful_parent_task_and_child_terminal(self):
        baseline = NativeHistory(
            root_id="ses_root",
            sessions={"ses_root": NativeExport(info={"id": "ses_root"}, messages=[])},
        )
        parent = NativeExport(
            info={"id": "ses_root"},
            messages=[
                {
                    "info": {
                        "id": "msg_user",
                        "role": "user",
                        "time": {"created": 200},
                    },
                    "parts": [],
                },
                {
                    "info": {
                        "id": "msg_root",
                        "role": "assistant",
                        "time": {"completed": 300},
                    },
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "task",
                            "callID": "task_call",
                            "state": {
                                "status": "completed",
                                "metadata": {
                                    "parentSessionId": "ses_root",
                                    "sessionId": "ses_child",
                                },
                            },
                        }
                    ],
                },
            ],
        )
        child = NativeExport(
            info={"id": "ses_child", "parentID": "ses_root", "time": {"created": 201}},
            messages=[
                {
                    "info": {
                        "id": "msg_child",
                        "role": "assistant",
                        "time": {"completed": 299},
                    },
                    "parts": [],
                }
            ],
        )
        history = NativeHistory(
            root_id="ses_root", sessions={"ses_root": parent, "ses_child": child}
        )
        command = NativeCommandInvocation(name="review", catalog_revision="a" * 64)
        self.assertEqual(
            OpenCodeCommands.result(command, history, baseline).native_terminal[
                "child_sessions"
            ],
            ["ses_child"],
        )
        parent.messages[-1]["parts"][0]["state"]["status"] = "error"
        with self.assertRaises(RunnerError):
            OpenCodeCommands.result(command, history, baseline)
        parent.messages[-1]["parts"][0]["state"]["status"] = "completed"
        child.messages[-1]["info"]["error"] = {"message": "Native child failed"}
        with self.assertRaises(RunnerError):
            OpenCodeCommands.result(command, history, baseline)

    def test_native_controller_tool_execution_cannot_count_as_command_success(self):
        baseline = NativeHistory(
            root_id="ses_root",
            sessions={"ses_root": NativeExport(info={"id": "ses_root"}, messages=[])},
        )
        history = NativeHistory(
            root_id="ses_root",
            sessions={
                "ses_root": NativeExport(
                    info={"id": "ses_root"},
                    messages=[
                        {
                            "info": {
                                "id": "msg",
                                "role": "assistant",
                                "time": {"completed": 300},
                            },
                            "parts": [
                                {
                                    "type": "tool",
                                    "tool": "bash",
                                    "callID": "unsafe",
                                    "state": {"status": "completed"},
                                }
                            ],
                        }
                    ],
                )
            },
        )
        with self.assertRaises(RunnerError):
            OpenCodeCommands.result(
                NativeCommandInvocation(name="init", catalog_revision="a" * 64),
                history,
                baseline,
            )
