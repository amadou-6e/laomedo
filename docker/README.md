# Registered container images

`images.json` is the trusted registry for automatic image acquisition. Each entry
names its image tag, context directory relative to this folder, Dockerfile,
explicit build inputs, fixed arguments and zero-turn version verification.
DockerRuntime builds only genuinely missing registered images on its selected
daemon. Existing mismatched recipes fail; explicit immutable pins remain strict.

The complete registered contexts are copied into wheel package resources at
build time. `container_images/models.py` owns validated registrations and immutable
recipe snapshots; `registry.py` loads source or packaged registrations; `lock.py`
provides cross-process per-daemon/image exclusion. `settings.py` owns build and
verification budgets. Shared launch/build operations stay on `DockerRuntime`.
No provider-specific build classes or request-supplied build paths are used.

## Existing installations

Images built before automatic acquisition do not carry the recipe label. Startup
refuses these existing tags. Remove the specific registered tag with
`docker image rm <registered-image:version>` after checking that it is no longer
needed; the next startup builds and verifies it. This also applies after changing
a registered recipe without changing its tag. Explicit image-ID overrides remain
local-only: a missing or mismatched pinned image fails without a network build.

BuildKit can download base images using the user's normal Docker registry login,
and the Dockerfile can download its declared dependencies. Provider credentials
are not supplied. Lock files and version-job recovery receipts live in the
owner-only `~/.laomedo-image-builds` directory. Verification has an ephemeral
64 MiB `/tmp` and no network or host mounts.

The OpenCode worker intentionally uses the Codex context because that existing
worker contract needs its Git, GitHub and Python tools. Its separate tag keeps
controller and worker registration explicit; Docker reuses shared build layers.
