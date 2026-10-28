"""Fixed, host-owned permission overrides for the disposable Git experiment."""

GIT_OVERRIDE = (
    'permissions={container-edit={filesystem={":root"="read",'
    '":workspace_roots"="write","/home/runner/.codex/auth.json"="deny",'
    '"/draft/.git"="write"},network={enabled=false}}}'
)

PROFILE_OVERRIDES = [
    "-c",
    'default_permissions="container-edit"',
    "-c",
    'approval_policy="never"',
    "-c",
    GIT_OVERRIDE,
]
