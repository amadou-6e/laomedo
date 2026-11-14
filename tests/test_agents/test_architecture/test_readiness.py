"""Common readiness facts from actual provider checks with explicit native doubles."""

from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, Mock, patch

from pydantic import ValidationError

from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.base.models import ReadinessObservation
from laomedo.agents.agents.claude.agent import ClaudeAgent
from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.agents.agents.opencode.agent import OpenCodeAgent
from laomedo.agents.errors import RunnerError
from laomedo.host.credentials.siwc.errors import AuthError


class ReadinessTests(unittest.TestCase):
    """Discovery, configuration and permission probes cannot substitute for auth."""

    def test_common_consumer_observes_each_providers_actual_scope(self):
        claude = object.__new__(ClaudeAgent)
        claude.profile = "dedicated-test-profile"
        claude.image_id = "sha256:" + "a" * 64
        codex = object.__new__(CodexAgent)
        native = {"status": "ready", "permission_checks": {"workspace_write": 0}}
        opencode = object.__new__(OpenCodeAgent)
        opencode.transport_factory = Mock()
        with (
            patch.object(claude, "_check_auth") as auth,
            patch.object(
                codex, "_preflight", new=AsyncMock(return_value=native)
            ) as probes,
        ):
            agents: list[BaseAgent] = [claude, codex, opencode]
            results = [agent.readiness() for agent in agents]
        auth.assert_called_once_with()
        probes.assert_awaited_once_with()
        self.assertEqual([result.ready for result in results], [True, None, None])
        self.assertEqual(
            [result.reason for result in results],
            [None, "authentication_not_verified", "opencode_transport_not_verified"],
        )
        self.assertEqual(
            [result.scope for result in results],
            [
                "native_subscription_authentication",
                "native_handshake_and_policy_probes",
                "transport_configuration_only",
            ],
        )
        self.assertEqual(results[1].payload, native)
        results[1].payload["permission_checks"]["workspace_write"] = 1
        self.assertEqual(native["permission_checks"]["workspace_write"], 0)
        for result in results:
            self.assertIsInstance(result, ReadinessObservation)
            self.assertNotIn("payload", result.model_dump())

    def test_missing_transport_has_a_specific_blocker_without_launch(self):
        agent = object.__new__(OpenCodeAgent)
        agent.transport_factory = None
        result = agent.readiness()
        self.assertIs(result.ready, False)
        self.assertEqual(result.reason, "opencode_isolated_transport_required")
        self.assertEqual(result.payload, agent.preflight())

    def test_native_failure_becomes_blocker_but_raw_preflight_still_raises(self):
        for kind, code in (
            (ClaudeAgent, "claude_subscription_unavailable"),
            (CodexAgent, "permission_preflight_failed"),
            (OpenCodeAgent, "opencode_transport_cleanup_failed"),
        ):
            with self.subTest(provider=kind.provider):
                agent = object.__new__(kind)
                with patch.object(
                    agent, "preflight", side_effect=RunnerError(code)
                ) as check:
                    result = agent.readiness()
                    self.assertIs(result.ready, False)
                    self.assertEqual(result.reason, code)
                    check.assert_called_once_with()
                    with self.assertRaisesRegex(RunnerError, code):
                        agent.preflight()

    def test_codex_token_borrow_refusal_is_an_explicit_blocker(self):
        agent = object.__new__(CodexAgent)
        with patch.object(
            agent,
            "_preflight",
            new=AsyncMock(side_effect=AuthError("auth_login_required")),
        ):
            result = agent.readiness()
        self.assertIs(result.ready, False)
        self.assertEqual(result.reason, "auth_login_required")

    def test_programming_errors_are_not_reported_as_expected_unavailability(self):
        agent = object.__new__(ClaudeAgent)
        with patch.object(
            agent, "preflight", side_effect=RuntimeError("unexpected bug")
        ):
            with self.assertRaisesRegex(RuntimeError, "unexpected bug"):
                agent.readiness()

    def test_incomplete_or_inconsistent_readiness_cannot_be_constructed(self):
        fields = dict(provider="example", scope="authentication", payload={})
        for ready in (False, None):
            with self.subTest(ready=ready):
                with self.assertRaises(ValidationError):
                    ReadinessObservation(ready=ready, **deepcopy(fields))
        with self.assertRaises(ValidationError):
            ReadinessObservation(ready=True, reason="blocked", **fields)
        with self.assertRaises(ValidationError):
            ReadinessObservation(ready="true", **fields)
