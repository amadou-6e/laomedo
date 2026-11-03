"""Host-service probe environment, distinct from a Git command's private home."""

import os


def host_environment() -> dict[str, str]:
    """Preserve the historical service process environment without Git overrides.

    Services need their ordinary home for their explicit local configuration. Git
    subprocesses instead use GitExecutionContext through the production runner.
    """
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "GCM_"))
        and key not in {"GH", "GH_TOKEN", "GITHUB_TOKEN", "SSH_ASKPASS"}
    }
    environment.update(
        GIT_CONFIG_GLOBAL=os.devnull,
        GIT_CONFIG_SYSTEM=os.devnull,
        GIT_CONFIG_NOSYSTEM="1",
        GIT_TERMINAL_PROMPT="0",
        GIT_ASKPASS="",
        GIT_NO_REPLACE_OBJECTS="1",
    )
    return environment
