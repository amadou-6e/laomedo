# Isolated graph runtime image

This image supplies the pinned native LFX executor for a single saved-account
job. It is not the credential broker and never contains profile databases,
Windows vault state, GitHub tokens, browser cookies or broker signing keys.
The host must launch it without host-state mounts or a Docker socket, under a
non-root user, with a read-only root filesystem and job-owned temporary storage.
An image alone does not establish those launch guarantees.

Prepare a clean build context from native revision
`fec71dca901949c09ed4d63315804337cd2eb13d`: export only its tracked `src/lfx`
and `src/sdk` trees, and export its frozen `uv.lock` runtime dependency selection for `lfx`
with hashes (`uv export --frozen --package lfx --no-dev --no-default-groups
--no-emit-workspace`). Put the exported dependency list in `requirements.txt`.
Copy this Dockerfile into that context. Do not build from a live private runtime,
copy an entire workspace with `.env`, or include native login state.

The official Linux/amd64 Python base is pinned by manifest digest. Runtime
dependencies come from the native lock export; the build backend version is
explicit. The Laomedo worker entry point, per-job channel, catalog checks and
independent cleanup supervision must be installed and verified before this base
can execute saved-account graphs. The default preview launcher is unchanged.
