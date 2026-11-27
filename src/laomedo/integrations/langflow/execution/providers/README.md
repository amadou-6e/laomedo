# Saved-provider graph execution

This capability adapts the shared isolated native worker to saved Agent accounts
and anonymous public Issue reads. It never starts a native Langflow application
inside the account broker. The isolated worker has no network, host mounts,
Docker socket, account stores, runner tokens or review grants.

## Layout and responsibilities

`models.py` owns the credential-free `ProviderWorkerJob`, per-vertex virtual
routes and private request/reply envelopes. The parent binds the job's pipe to
`ProviderGraphRuns`; its actual capability never crosses into the worker.
`channel.py` owns `ProviderWorkerChannel` and its local HTTP-compatible adapter.
The adapter forwards only this job's virtual vertex/path/body on the private
pipe; it cannot open a host URL. `native.py` specializes `NativeGraphWorker` so
the same catalog/digest/constructor checks run before component instantiation.

`dispatcher.py` owns host-only `ProviderGraphDispatcher`: it derives profile,
account generation, model/effort, source run and host request UUID from the
approved plan. Starts use the controller's gated native reservation. Review
staging keeps patch bytes, native requests and grants in the host; only the
semantic hash reaches the worker. Reads and cancellation resolve only a run
acknowledged under the requested vertex. Worker aliases never become native
request authority. Anonymous Issue dispatch uses only a host-approved public
selection and the credential-free REST transport.

`container.py` specializes the shared sandbox supervisor hooks and private
exchange. It validates the actual graph, checks lease/deadline while requests
are active, revokes before cleanup, and cancels only this job's native request
receipts. The shared supervisor remains the single owner of container hardening,
lease registration, inspection and exact cleanup. Normal native run history
survives job revocation; unknown cancellation is never claimed as settlement.

This integration is under development. The ordinary native-process review
binding remains disabled until the isolated app and actual graph path are
verified. Host policy/dispatcher tests are separate from real container and
model-backed end-to-end acceptance.
