"""Host-owned registration of concrete providers and their supported capabilities."""

from laomedo.agents.models import AgentProviderDescriptor


class AgentProviderRegistry:
    """Resolve only trusted built-ins; input never supplies imports or factories.

    Descriptor lookup does not import optional provider dependencies, read login
    state or start a process. Construction is explicit through create_agent.
    """

    @classmethod
    def descriptors(cls) -> tuple[AgentProviderDescriptor, ...]:
        """Return the closed built-in identities with existing capability differences."""
        return (
            AgentProviderDescriptor(
                provider="codex",
                display_name="Codex",
                managed_startup=True,
                join_bridge=True,
                output_requirements=True,
            ),
            AgentProviderDescriptor(
                provider="claude",
                display_name="Claude",
                managed_startup=True,
                join_bridge=True,
                output_requirements=True,
            ),
            AgentProviderDescriptor(
                provider="opencode",
                display_name="OpenCode",
                managed_startup=False,
                join_bridge=False,
                output_requirements=False,
            ),
        )

    @classmethod
    def provider_ids(cls) -> frozenset[str]:
        """Return registered IDs without loading a concrete provider implementation."""
        return frozenset(item.provider for item in cls.descriptors())

    @classmethod
    def descriptor(cls, provider: str) -> AgentProviderDescriptor:
        """Read a registered identity or reject unknown input before factory lookup."""
        for item in cls.descriptors():
            if item.provider == provider:
                return item
        raise ValueError("unregistered_agent_provider")

    @classmethod
    def create_agent(cls, provider: str, *args, **kwargs):
        """Construct a registered Agent from trusted host-owned constructor arguments.

        Provider constructors retain their native readiness, recovery and failure
        behavior. This is a host composition API, never a graph argument surface.
        """
        cls.descriptor(provider)
        if provider == "codex":
            from laomedo.agents.agents.codex.agent import CodexAgent

            factory = CodexAgent
        elif provider == "claude":
            from laomedo.agents.agents.claude.agent import ClaudeAgent

            factory = ClaudeAgent
        else:
            from laomedo.agents.agents.opencode.agent import OpenCodeAgent

            factory = OpenCodeAgent
        return factory(*args, **kwargs)
