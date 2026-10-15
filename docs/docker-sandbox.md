# Docker runner sandbox startup

The legacy Codex runner packages a pinned Moby seccomp allowlist with narrow
namespace/mount additions for Bubblewrap. This resolves namespace failures on
Docker Desktop versions whose default profile rejects Bubblewrap startup.
It retains a default-deny policy, non-root UID 10001, all capabilities dropped,
no-new-privileges, the fixed Codex version and the inner permission profile.
Missing or changed seccomp resources refuse launch. See the packaged
[policy provenance](../laomedo/resources/codex-seccomp.md) and upstream license.
The split controller's policy is unchanged.

Rebuild the fixed CLI version using the repository Dockerfile when the original
machine-local image is unavailable. Builds may have different image identities
because package repositories and build metadata change. Review the new artifact,
verify `codex --version`, and obtain its full SHA256 ID using `docker image inspect`.
An operator may supply that exact approved ID with `--image-id` for a non-Git
runner. This is trusted host startup configuration, never a graph/run API field.
The fixed version tag must still match exactly; launch uses the immutable ID,
and the CLI version check remains enforced. Defaults and historical pins stay
unchanged. Git-image overrides are not supported by this option.

Run native `--preflight` before granting model turns. It must allow the workspace
write and deny canonical/store writes and credential reads; if all commands fail,
that is broken sandbox startup, not proof of protected-path isolation. A real
model run is still necessary to establish integration acceptance. Keep local test
authentication outside Git and follow the workspace's credential-copy policy.
