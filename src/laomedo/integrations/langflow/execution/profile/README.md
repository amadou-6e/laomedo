# Per-profile native API runtime

This package runs one untrusted, network-free native Langflow API container per
profile, holding that profile's operational graph state. It is not the
credential broker and has no GitHub, broker or job authority.

## Layout and objects

```text
profile/
  __main__.py   container entry point (python -m laomedo.integrations.langflow.execution.profile)
  settings.py   NATIVE_PROFILE_* values, NativeProfileSettings,
                NativeProfileDeploymentSettings
  models.py     NativeProfileInstance
  errors.py     NativeProfileError
  native.py     NativeProfileRuntime (runs inside the container)
  container.py  DockerProfileRuntime (host supervisor)
```

## Host supervisor

`container.py` owns `DockerProfileRuntime`. `acquire` admits a current owner and
returns its running instance, starting one if needed; an instance whose lease was
lost or that was stopped is removed and replaced rather than refusing the owner
indefinitely. `stop` removes only that owner's exact container, and `close` ends
this broker's instances. A named local volume is scoped to the explicit
deployment UUID and owner UUID; container cleanup never deletes persisted
operational history. Volume labels, driver and mount identity are verified, and
no host directory is mounted. The native API's loopback readiness check is not
broker authentication. Failures raise `NativeProfileError` (code
`graph_profile_runtime_unavailable`), separate from the job worker's error.

`NativeProfileInstance` is an internal lifetime record (container identity,
volume, lease, cancellation event); it is never parsed from browser data or
returned as authority. `NativeProfileDeploymentSettings` adds the deployment
namespace, readiness timeout and native API limits to `BaseDockerRuntimeSettings`;
its `image_id` is the native API runtime image digest.

## In-container application

`native.py` owns `NativeProfileRuntime`, an untrusted native API application for
one profile's operational graph state. `create_app` configures only that separate
store and the native data identity; `lifespan` creates its ordinary operational
user and default folder. `current_user` resolves the container's fixed owner,
never a browser assertion. This identity has no authority in the credential
broker. The container must have no network, broker state or job capabilities;
trusted host admission and a private transport must precede every forwarded API
request. This application must never be mounted in the broker or exposed
directly. `__main__.py` is its container-only entry point, used by
`Dockerfile.runtime`. The browser proxy and normal UI launcher are not wired to
it yet.
