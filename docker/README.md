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
