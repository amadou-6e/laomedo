# Agent activity

`GraphAgents` composes graph execution selection and the selected Agent run. Wire records belong to models.ts; pure projection, timing, filtering and export operations belong to utils.ts. Components render retained conversation, usage and telemetry. Viewing does not dispatch a model. `AgentActivity` is the native receipt modal; `AgentActivityNavigation` owns the app navigation store.

The main Activity scroll area ends with a muted MIT copyright footer, separated
from the conversation by generous spacing and followed by bottom padding.
