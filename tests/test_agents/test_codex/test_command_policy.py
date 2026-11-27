"""Native command policy controls, independent of model-backed acceptance."""

import unittest
from pydantic import ValidationError
from laomedo.agents.agents.base.models import NativeCommandInvocation
from laomedo.agents.agents.codex.commands import CodexCommands
from laomedo.agents.errors import RunnerError


class NativeCommandPolicyTests(unittest.TestCase):
    """Discovery is not permission and arguments cannot smuggle another prompt."""

    def test_builtin_policy_and_argument_boundaries(self):
        """Only implemented built-ins receive an explicit native completion class."""
        for name, kind in (
            ("status", "control"),
            ("mcp", "control"),
            ("skills", "control"),
            ("review", "turn"),
            ("compact", "turn"),
        ):
            request = NativeCommandInvocation(name=name, catalog_revision="a" * 64)
            self.assertEqual(CodexCommands.validate(request), kind)
            if name != "review":
                with self.assertRaises(RunnerError):
                    CodexCommands.validate(
                        request.model_copy(update={"arguments": "extra"})
                    )
        for name in (
            "logout",
            "rename",
            "goal",
            "plan",
            "review-branch",
            "review-commit",
            "custom",
        ):
            with self.assertRaises(RunnerError):
                CodexCommands.validate(
                    NativeCommandInvocation(name=name, catalog_revision="a" * 64)
                )
        for value in ("one\ntwo", "one\rtwo", "one\x00two", "one\u2028two"):
            with self.assertRaises(ValidationError):
                NativeCommandInvocation(
                    name="review", arguments=value, catalog_revision="a" * 64
                )

    def test_observed_unknown_command_is_not_admitted(self):
        """Native advertisements cannot expand the host's fixed execution policy."""
        result = CodexCommands.project(
            {"commands": [{"name": "logout", "description": "Sign out"}]}
        )
        self.assertFalse(result["commands"][0]["executable"])
        self.assertEqual(
            result["commands"][0]["reason"], "outside_assistant_command_policy"
        )
