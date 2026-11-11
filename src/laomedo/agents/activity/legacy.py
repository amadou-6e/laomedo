"""Read-only interpretation of previously retained native evidence, not new ingestion."""


def project_retained(events, *, provider, root_thread, model):
    """Keep saved Activity readable without constructing a live provider Agent.

    Only old database receipts use this path. New Activity pages already contain
    normalized records and a shared display projection, with no parser selection.
    """
    if provider is None:
        methods = [
            str(row.get("raw", {}).get("event", row.get("raw", {})).get("method", ""))
            for row in events
        ]
        provider = (
            "opencode"
            if any(value.startswith("opencode/") for value in methods)
            else (
                "claude"
                if any(value.startswith("claude/") for value in methods)
                else "codex"
            )
        )
    if provider in {"opencode"}:
        from laomedo.agents.agents.opencode.activity.projection import project

        return project(events, root_thread=root_thread, model=model)
    if provider in {"claude", "claude-code"}:
        from laomedo.agents.agents.claude.activity.projection import project
    elif provider in {"codex", "codex-cli", None}:
        from laomedo.agents.agents.codex.activity.projection import project
    else:
        raise ValueError("unregistered_activity_provider")
    return project(events, root_thread=root_thread, model=model).to_payload()
