"""Verify host-controlled identities and actual capability-aware construction."""

import unittest
from unittest.mock import patch
from laomedo.agents.registry import AgentProviderRegistry
from laomedo.agents.interface.models import SUPPORTED_PROVIDERS


class ProviderRegistrationTests(unittest.TestCase):
    def test_unregistered_input_cannot_resolve_a_factory(self):
        """Import-looking IDs and unknown providers refuse before construction."""
        for provider in ("module.Factory", "../codex", "", "unknown"):
            with self.subTest(provider=provider):
                with self.assertRaisesRegex(ValueError, "unregistered_agent_provider"):
                    AgentProviderRegistry.create_agent(provider)

    def test_host_factory_uses_registered_provider_and_exact_arguments(self):
        """No external ID can redirect a provider's fixed defining-class import."""
        for provider, name in (
            ("codex", "CodexAgent"),
            ("claude", "ClaudeAgent"),
            ("opencode", "OpenCodeAgent"),
        ):
            with self.subTest(provider=provider):
                target = f"laomedo.agents.agents.{provider}.agent.{name}"
                with patch(target) as factory:
                    created = AgentProviderRegistry.create_agent(
                        provider, "state", lease_service="lease"
                    )
                    self.assertIs(created, factory.return_value)
                    factory.assert_called_once_with("state", lease_service="lease")

    def test_capability_differences_and_wire_ids_are_preserved(self):
        """Closed IDs match wire validation without claiming unsupported startup."""
        self.assertEqual(SUPPORTED_PROVIDERS, AgentProviderRegistry.provider_ids())
        self.assertTrue(AgentProviderRegistry.descriptor("claude").managed_startup)
        self.assertTrue(AgentProviderRegistry.descriptor("codex").join_bridge)
        descriptor = AgentProviderRegistry.descriptor("opencode")
        self.assertFalse(descriptor.output_requirements)
        self.assertFalse(descriptor.managed_startup)
        self.assertFalse(descriptor.join_bridge)
