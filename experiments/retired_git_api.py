"""Explicit refusal for historical probes, never a production compatibility path."""


def refuse_private_git_api(*_args, **_kwargs):
    """Stop before an old helper can expose credentials or start a Git operation."""
    raise RuntimeError(
        "Historical experiment: private Git process helpers were removed. "
        "Migrate to laomedo.git and revalidate effect authorization before running."
    )
