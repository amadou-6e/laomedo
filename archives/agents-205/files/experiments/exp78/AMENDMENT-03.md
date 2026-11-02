# EXP-78 amendment 03: pinned Docker runtime comparison

The independently reviewed installed-CLI observation covers Codex 0.155,
while the local runner pins 0.159.2 in Docker. Before running the product
comparison, use the same synthetic fixture and `initialize` plus
`skills/list` request, with no credential and zero turns, in the already
installed image by its exact image ID. Mount only the disposable fixture
project read-only; use a read-only root filesystem, private tmpfs HOME and
CODEX_HOME, no network, a non-root UID, dropped capabilities and no new
privileges. Record the image ID, CLI version, source/effective/post hashes,
sanitized native listing, path classes and whether the exact temporary
container was removed. Never mount the host profile, Docker socket, or
Laomedo source tree. Treat a listed fixture as `offered`, not `used`.
