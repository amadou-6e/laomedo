"""Compose registered Activity interpretation at the existing wire boundary."""

from laomedo.agents.registry import AgentProviderRegistry


def project(events, *, root_thread=None, model=None, provider=None):
    """Return the current payload using stored identity or native receipt markers.

    Stored provider identity takes precedence over content. Internal unqualified
    callers retain native-marker selection for existing normalized observations.
    No provider-native parsing or pricing is implemented in this shared path.
    """
    projector = (
        AgentProviderRegistry.activity_projector(provider)
        if provider is not None
        else AgentProviderRegistry.projector_for_events(events)
    )
    value = projector.project(events, root_thread=root_thread, model=model)
    if projector.usage_first_payload:
        return value.to_usage_first_payload()
    return value.to_payload()
