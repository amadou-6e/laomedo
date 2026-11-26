"""Current optional quota capability and inert provider composition contracts."""

import inspect
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

from laomedo.agents.agents.base.base import BaseSubscriptionQuota
from laomedo.agents.agents.base.agent import BaseAgent
from laomedo.agents.agents.claude.quota import ClaudeSubscriptionQuota
from laomedo.agents.agents.codex.quota import CodexSubscriptionQuota
from laomedo.agents.agents.opencode.quota import OpenCodeSubscriptionQuota
from laomedo.agents.registry import AgentProviderRegistry


class SubscriptionQuotaContractTests(TestCase):
    """Providers share the read contract without requiring unsupported agent behavior."""

    def test_read_is_required_and_all_registered_readers_implement_it(self):
        self.assertTrue(inspect.isabstract(BaseSubscriptionQuota))
        with self.assertRaises(TypeError):
            BaseSubscriptionQuota()
        for reader in (
            ClaudeSubscriptionQuota,
            CodexSubscriptionQuota,
            OpenCodeSubscriptionQuota,
        ):
            with self.subTest(reader=reader.__name__):
                self.assertTrue(issubclass(reader, BaseSubscriptionQuota))
                self.assertFalse(inspect.isabstract(reader))

    def test_capability_construction_performs_no_provider_operation(self):
        agent = Mock()
        ClaudeSubscriptionQuota(agent)
        CodexSubscriptionQuota(agent)
        with patch("laomedo.agents.agents.opencode.quota.subprocess.run") as run:
            OpenCodeSubscriptionQuota(Path("unused-profile"))
            run.assert_not_called()
        self.assertEqual(agent.mock_calls, [])
        self.assertIsNone(BaseAgent.quota.fget(agent))

    def test_registry_selects_supported_credential_methods_without_startup(self):
        for provider, method in (
            ("codex", "codex-native"),
            ("claude", "claude-native"),
            ("opencode", "opencode-go"),
        ):
            self.assertTrue(
                AgentProviderRegistry.supports_subscription_quota(provider, method)
            )
            self.assertFalse(
                AgentProviderRegistry.supports_subscription_quota(
                    provider, "unregistered-method"
                )
            )
        self.assertFalse(
            AgentProviderRegistry.supports_subscription_quota(
                "unregistered-provider", "codex-native"
            )
        )
