# Agent activity

`GraphAgents` composes graph execution selection and the selected Agent run. Wire records belong to models.ts; pure projection, timing, filtering and export operations belong to utils.ts. Components render retained conversation, usage and telemetry. Viewing does not dispatch a model. `AgentActivity` is the native receipt modal; `AgentActivityNavigation` owns the app navigation store.

The selected run shows its conversation before usage and runtime diagnostics.
Conversation messages use the main Activity panel's scrolling area, so reaching a
reply does not require finding a second scrollbar inside the transcript.
