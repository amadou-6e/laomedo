"""Host-owned provider composition and private conversation identity."""

import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from pydantic import ValidationError
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import ConversationRequest
from laomedo.integrations.langflow.assistant.runner import AssistantRunner
from laomedo.integrations.langflow.assistant.runtime import AssistantRuntime
from laomedo.integrations.langflow.assistant.settings import AssistantSettings


class ProviderCompositionTests(unittest.TestCase):
    """Fixture composition performs no Docker, credential or inference operations."""

    def test_private_provider_bindings_are_not_serialized_or_represented(self):
        with tempfile.TemporaryDirectory() as temporary:
            profile = Path(temporary) / "private-auth"
            settings = AssistantSettings(
                opencode_profile=profile, claude_profile_volume="laomedo-claude-chat"
            )
            self.assertNotIn(str(profile), repr(settings))
            self.assertNotIn("opencode_profile", settings.model_dump())
            self.assertNotIn("claude_profile_volume", settings.model_dump())
        with self.assertRaises(ValidationError):
            AssistantSettings(opencode_profile="relative/profile")
        with self.assertRaises(ValidationError):
            ConversationRequest(provider="other", model="model", effort="default")

    def test_codex_key_stays_stable_and_other_provider_keys_are_distinct(self):
        owner = uuid4()
        self.assertEqual(AssistantRuntime._runner_key(owner, "codex"), owner)
        self.assertNotEqual(AssistantRuntime._runner_key(owner, "claude"), owner)
        self.assertNotEqual(
            AssistantRuntime._runner_key(owner, "claude"),
            AssistantRuntime._runner_key(owner, "opencode"),
        )

    def test_provider_construction_uses_private_roots_and_only_host_bindings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            owner = uuid4()
            settings = AssistantSettings(
                app_url="http://127.0.0.1:17881",
                state_root=root,
                claude_profile_volume="laomedo-claude-chat",
                opencode_profile=root / "private-profile",
            )
            config = {
                "provider": "codex",
                "skill_store": str(root / "skills"),
                "lease_service": str(root / "lease"),
            }
            namespace = hashlib.sha256(settings.app_url.encode()).hexdigest()[:16]
            for provider in ("codex", "claude", "opencode"):
                expected = root / namespace / str(owner)
                if provider != "codex":
                    expected = expected / provider
                (expected / "source-repository/.git").mkdir(parents=True)
                with (
                    patch(
                        "laomedo.integrations.langflow.assistant.runner.RunnerService.config",
                        return_value=config,
                    ),
                    patch(
                        "laomedo.integrations.langflow.assistant.runner.prepare_private_directory"
                    ),
                    patch(
                        "laomedo.integrations.langflow.assistant.runner.AgentProviderRegistry.create_agent"
                    ) as create,
                    patch(
                        "laomedo.integrations.langflow.assistant.runner.RunnerServer"
                    ) as server,
                ):
                    server.return_value.server_address = ("127.0.0.1", 12345)
                    runner = AssistantRunner(settings, owner, provider)
                    runner.start()
                    self.assertEqual(
                        create.call_args.args[:2], (provider, expected / "runner")
                    )
                    if provider == "claude":
                        self.assertEqual(
                            create.call_args.kwargs["profile_volume"],
                            "laomedo-claude-chat",
                        )
                    if provider == "opencode":
                        self.assertEqual(
                            create.call_args.kwargs["profile"],
                            settings.opencode_profile,
                        )
                    runner.shutdown()

    def test_unconfigured_provider_refuses_before_construction(self):
        settings = AssistantSettings(app_url="http://127.0.0.1:17881")
        config = {"provider": "codex"}
        with (
            patch(
                "laomedo.integrations.langflow.assistant.runner.RunnerService.config",
                return_value=config,
            ),
            patch(
                "laomedo.integrations.langflow.assistant.runner.AgentProviderRegistry.create_agent"
            ) as create,
        ):
            for provider in ("claude", "opencode", "other"):
                with self.assertRaises(AssistantError):
                    AssistantRunner(settings, uuid4(), provider).start()
            create.assert_not_called()
