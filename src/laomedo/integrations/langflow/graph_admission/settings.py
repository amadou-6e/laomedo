"""Host-owned execution classification; never inferred from browser payloads."""

# An explicit classification, not a name-based inference from browser payloads.
# Add a canonical host catalog type only after checking its execution behavior.
# Unknown types (including code interpreters and runtime flow loaders) refuse.
GITHUB_GRAPH_COMPONENT_TYPES = frozenset(
    {
        "LaomedoGitHubIssue",
        "LaomedoGitHubPR",
        "LaomedoCodexAgent",
        "LaomedoClaudeAgent",
        "LaomedoOpenCodeAgent",
        "LaomedoSkill",
        "LaomedoHandoff",
        "LaomedoOutputContract",
        "LaomedoBoundedController",
        "ChatInput",
        "ChatOutput",
        "TextInput",
        "TextOutput",
        "Prompt",
        "Prompt Template",
    }
)
