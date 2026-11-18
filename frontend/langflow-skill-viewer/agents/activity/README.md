# Agent activity

`GraphAgents` composes graph execution selection and the selected Agent run. Wire records belong to models.ts; pure projection, timing, filtering and export operations belong to utils.ts. Components render retained conversation, usage and telemetry. Viewing does not dispatch a model. `AgentActivity` is the native receipt modal; `AgentActivityNavigation` owns the app navigation store.

The main Activity scroll area ends with a muted MIT copyright footer, separated
from the conversation by generous spacing and followed by bottom padding.

An active invocation's main conversation shows "starting" until its first
turn is captured. Observed turn states and terminal invocation failures retain
their own status; an absent turn is not itself a failure.

Owner feedback #295 (ACT-295 in run-traces/design/agent-activity.drawio): each
telemetry/conversation heading has an icon-only search toggle. Opening focuses
the field; closing/Escape clears hidden filters, Escape returns focus to the
icon, and Clear keeps the field open. Scope changes remount these components.
Empty telemetry is centered text without a bordered card. Usage has an extra
16 px top padding above the existing 24 px section gap. No capture/dispatch or
export contract changes.
