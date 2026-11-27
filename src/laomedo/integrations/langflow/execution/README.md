# Isolated native graph execution

This capability runs untrusted native Langflow code outside the credential
broker. It owns two separate runtimes that share only local-Docker control:

- [`worker/`](worker/README.md): one fresh container per admitted saved-account
  job, talking to the broker over a private pipe.
- [`profile/`](profile/README.md): one long-lived, network-free native API
  container per profile for operational graph state.

Neither runtime owns profile identity, GitHub tokens or mediation grants. The
implementation is incomplete and is not connected to the ordinary preview
launcher, browser admission or the canvas.

## Shared layout

```text
execution/
  base.py      BaseDockerRuntime
  settings.py  BaseDockerRuntimeSettings, DOCKER_CONTROL_* bounds
  errors.py    GraphRuntimeError
  utils.py     private_state_path
  worker/      single-job worker (see its README)
  profile/     per-profile native API (see its README)
```

`base.py` owns `BaseDockerRuntime`, shared local-daemon control. Its control
methods filter the client environment, bound subprocess I/O, verify the local
context and inspect/remove only exact labelled container identities.
`_hardening_arguments` is the single definition of the sandbox flags every
container is created with, and `_verify_limits` checks the same values on the
created container; the two must change together. `_start_lease` begins
independent lease registration. Shared control raises the subclass's
`runtime_error`, so callers see `GraphWorkerError` or `NativeProfileError`.
Subclasses keep their own mount and authority policy; shared transport never
chooses an owner or creates a grant.

`_local_context` resolves and verifies the literal local daemon endpoint, removes
the mutable context selector from that job's control environment, and pins
`DOCKER_HOST` for subsequent create/inspect/remove calls. Both worker and profile
reservations carry the same endpoint into `LeaseClient`, so independent cleanup
cannot silently follow a retargeted Docker context. A service's `service.json`
publication, after its initial heartbeat pair, is its startup-ready receipt.

`settings.py` owns `BaseDockerRuntimeSettings`: image digest, lease state, Docker
context, resource limits and control timeout, accepted only from explicit host
arguments. Each runtime subclasses it with its own defaults and fields.
`errors.py` defines `GraphRuntimeError`, the common parent of both runtimes'
errors. `utils.py` holds `private_state_path`, which refuses relative paths,
symlinks/reparse points and repository-owned state without depending on Python
3.12-only path methods.

Images built before this layout run the retired entry points; rebuild
`docker/graph-worker/Dockerfile.worker` and `Dockerfile.runtime` after updating.
