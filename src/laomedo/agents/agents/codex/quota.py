"""Codex quota orchestration through the existing discovery lifecycle."""

import asyncio
from laomedo.agents.agents.base.base import BaseSubscriptionQuota
from laomedo.agents.agents.base.models import SubscriptionSnapshot


class CodexSubscriptionQuota(BaseSubscriptionQuota):
    """Retain native custody and exact discovery teardown around a zero-turn read."""

    def __init__(self, agent):
        """Bind the existing agent without launching a native process."""
        self.agent = agent

    def read(self) -> SubscriptionSnapshot:
        """Return only after the provider's discovery scope has closed."""
        return asyncio.run(self._read())

    async def _read(self) -> SubscriptionSnapshot:
        """Keep native protocol decoding inside CodexAgentRuntime."""
        async with self.agent._discovery("quota") as server:
            return await server.subscription_limits()
