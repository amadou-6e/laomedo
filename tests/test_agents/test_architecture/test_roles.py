"""Provider role outcomes protect current lifecycle/privacy/capability semantics."""

import asyncio
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pydantic import SecretStr, ValidationError
from laomedo.agents.agents.base.base import (
    BaseCommandExecutor,
    BaseInterruptibleCommandExecutor,
    BaseSplitCommandExecutor,
    BaseCredentialProvider,
    BaseModelCatalog,
)
from laomedo.agents.agents.base.models import (
    CommandRequest,
    CredentialRequest,
    CredentialMaterial,
    CredentialBinding,
)
from laomedo.agents.agents.codex.runtime import CodexAgentRuntime
from laomedo.agents.agents.claude.runtime import ClaudeAgentRuntime
from laomedo.agents.agents.claude.executor import ClaudeCommandExecutor
from laomedo.agents.agents.opencode.executor import OpenCodeCommandExecutor
from laomedo.agents.agents.codex.split.executor import CodexCommandExecutor
from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime
from laomedo.agents.agents.codex.credentials import CodexCredentialProvider
from laomedo.agents.agents.claude.credentials import ClaudeCredentialProvider
from laomedo.agents.agents.opencode.credentials import OpenCodeCredentialProvider
from laomedo.agents.agents.codex.activity.cost import estimate
from laomedo.agents.agents.claude.activity.projection import estimate as claude_estimate
from laomedo.agents.agents.opencode.activity.projection import estimate_native
from laomedo.agents.registry import AgentProviderRegistry
from laomedo.agents.errors import RunnerError


class ProviderRoleTests(unittest.TestCase):
    def test_command_capabilities_are_explicit_and_cancellation_is_not_acknowledgement(
        self,
    ):
        """Persistent split checks differ from interruptible transient job control."""
        self.assertTrue(issubclass(CodexCommandExecutor, BaseSplitCommandExecutor))
        self.assertFalse(
            issubclass(CodexCommandExecutor, BaseInterruptibleCommandExecutor)
        )
        for executor_type in (ClaudeCommandExecutor, OpenCodeCommandExecutor):
            self.assertTrue(issubclass(executor_type, BaseInterruptibleCommandExecutor))
            for active in (False, True):
                with self.subTest(provider=executor_type.__name__, active=active):
                    executor = executor_type.__new__(executor_type)
                    executor.lock = threading.Lock()
                    executor.capacity = threading.BoundedSemaphore(1)
                    executor.stopping = threading.Event()
                    executor.closed = False
                    gate = (
                        executor.lock
                        if executor_type is ClaudeCommandExecutor
                        else executor.capacity
                    )
                    if active:
                        gate.acquire()
                    try:
                        observed = executor.request_cancel()
                    finally:
                        if active:
                            gate.release()
                    self.assertEqual(observed.requested, active)
                    self.assertIsNone(observed.confirmed)
                    self.assertTrue(executor.stopping.is_set())
                    self.assertTrue(executor.closed)

    def test_borrow_contract_preserves_native_secret_ownership(self):
        """Each provider returns material without forcing volume secrets into tokens."""
        connection = Mock()
        connection.access_token.return_value = (
            "private-test-token",
            {"credential_ref": "host-account", "auth_outcome": "authenticated"},
        )
        codex = CodexCredentialProvider(SimpleNamespace(auth=connection))
        claude = ClaudeCredentialProvider(SimpleNamespace())
        opencode = OpenCodeCredentialProvider("admitted-profile")
        with (
            patch(
                "laomedo.agents.agents.claude.credentials.Settings",
                return_value=SimpleNamespace(mirror_host_login="0"),
            ),
            patch(
                "laomedo.agents.agents.opencode.credentials.check_auth_fresh"
            ) as check_profile,
        ):
            for provider in (codex, claude, opencode):
                with self.subTest(provider=type(provider).__name__):
                    material = provider.borrow()
                    self.assertIsInstance(material, CredentialMaterial)
                    self.assertNotIn("token", material.model_dump())
                    if provider is codex:
                        self.assertEqual(
                            material.native_pair()[0], "private-test-token"
                        )
                    else:
                        self.assertIsNone(material.token)
                    self.assertTrue(provider.release().confirmed)
        connection.access_token.assert_called_once_with()
        check_profile.assert_called_once_with("admitted-profile")

    def test_runtime_check_results_preserve_scope_and_unsupported_unknown(self):
        """Absent split checks remain unknown; native scoped results reach callers."""
        runtime = CodexAgentRuntime.__new__(CodexAgentRuntime)
        runtime.authorization_probe = None
        runtime.executor = None
        runtime.session = object()
        self.assertIsNone(runtime.check_health().alive)
        self.assertIsNone(runtime.assert_controller_isolated().verified)
        runtime.executor = SimpleNamespace(
            check_health=Mock(), assert_controller_isolated=Mock()
        )
        health = runtime.executor.check_health.return_value
        isolation = runtime.executor.assert_controller_isolated.return_value
        self.assertIs(runtime.check_health(), health)
        self.assertIs(runtime.assert_controller_isolated(), isolation)
        runtime.executor.assert_controller_isolated.assert_called_once_with(
            runtime.session
        )

    def test_role_contracts_are_actual_abstract_boundaries(self):
        """An incomplete provider cannot silently inherit a success implementation."""
        for role in (
            BaseCommandExecutor,
            BaseCredentialProvider,
            BaseModelCatalog,
        ):
            with self.subTest(role=role.__name__):
                with self.assertRaises(TypeError):
                    role()

    def test_command_requires_one_representation_and_finite_deadline(self):
        """Shell text and fixed argv stay explicit, without bool/NaN coercion."""
        for value in (
            {},
            {"command": "pwd", "argv": ["pwd"]},
            {"argv": []},
            {"command": "pwd", "deadline": float("nan")},
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    CommandRequest(**value)
        self.assertEqual(CommandRequest(argv=["pwd"]).argv, ["pwd"])

    def test_native_cleanup_uncertainty_survives_repeated_close(self):
        """A repeated close must preserve the prior exact resource cleanup failure."""
        runtime = CodexAgentRuntime.__new__(CodexAgentRuntime)
        runtime._closed = True
        runtime._close_failure = RunnerError("container_termination_unverified")
        for _ in range(2):
            with self.assertRaisesRegex(
                RunnerError, "container_termination_unverified"
            ):
                asyncio.run(runtime.close())
        from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime

        runtime = OpenCodeAgentRuntime.__new__(OpenCodeAgentRuntime)
        runtime.closing = True
        runtime.termination_verified = False
        for _ in range(2):
            with self.assertRaisesRegex(
                RunnerError, "opencode_container_cleanup_unverified"
            ):
                runtime.close()

    def test_claude_native_context_propagates_body_and_cleanup_failures(self):
        """Context exit retains original exception delivery and cleanup failures."""
        from contextlib import contextmanager

        observed = []

        @contextmanager
        def scope(*args):
            try:
                yield "native session"
            except ValueError as error:
                observed.append(str(error))
                raise

        policy = SimpleNamespace(_session_context=scope)
        with self.assertRaisesRegex(ValueError, "body failure"):
            with ClaudeAgentRuntime(policy, object(), "receipt", 10) as session:
                self.assertEqual(session, "native session")
                raise ValueError("body failure")
        self.assertEqual(observed, ["body failure"])

        @contextmanager
        def broken_scope(*args):
            try:
                yield "session"
            finally:
                raise RunnerError("container_termination_unverified")

        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            with ClaudeAgentRuntime(
                SimpleNamespace(_session_context=broken_scope), object(), "receipt", 10
            ):
                pass

    def test_credentials_are_private_and_unsupported_constraints_refuse_before_refresh(
        self,
    ):
        """Borrowed login is not revoked and secrets have only an explicit host projection."""
        connection = Mock()
        provider = CodexCredentialProvider(SimpleNamespace(auth=connection))
        with self.assertRaisesRegex(RunnerError, "credential_constraints_unsupported"):
            provider.prepare(CredentialRequest(minimum_validity_seconds=100.0))
        connection.access_token.assert_not_called()
        self.assertTrue(provider.release().confirmed)
        connection.revoke.assert_not_called()
        value = CredentialMaterial(
            token=SecretStr("sensitive-canary"),
            binding=CredentialBinding(
                credential_mode="test", credential_ref=None, auth_outcome="unknown"
            ),
        )
        self.assertNotIn("sensitive-canary", repr(value))
        self.assertNotIn("token", value.model_dump())
        self.assertEqual(value.native_pair()[0], "sensitive-canary")
        provider = OpenCodeCredentialProvider("not-opened")
        with self.assertRaisesRegex(RunnerError, "credential_constraints_unsupported"):
            provider.validate(CredentialRequest(deadline=1.0))

    def test_provider_pricing_cannot_fall_back_to_codex_rates(self):
        """A known Codex model name does not certify another provider's prices."""
        usage = {"inputTokens": 100, "cachedInputTokens": 0, "outputTokens": 5}
        self.assertIsNotNone(estimate("gpt-6-luna", usage)["amount"])
        self.assertIsNone(claude_estimate("gpt-6-luna", usage)["amount"])
        self.assertIsNone(estimate_native("gpt-6-luna", usage, None)["amount"])
