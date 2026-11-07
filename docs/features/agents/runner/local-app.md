# Open the local app with Codex recovery configured

Use `laomedo-app` for a prepared native, single-user, loopback installation.
It replaces the hand-written environment/bootstrap block for Codex and binds
the app's recovery manager, Agent token file, registry and new-node runner URL
to the same trusted runner-service configuration. It does not install Langflow,
build the frontend, start Docker or provision provider login. The full first-use
launcher remains tracked in issue #204.

## Prepare the existing installation

Install Laomedo's `runner` extra in the app's Python environment, alongside
Langflow 1.12.3, matching `langflow-base`/`lfx` 1.12.3 and the matching built
Laomedo frontend. Keep the existing Langflow state directory to preserve saved
graphs and signing keys. Use a registry and runner state outside Git.

Docker must be available, the [Codex image](../../../../docker/codex/README.md)
must have passed its normal pin/version checks, and the dedicated Codex login
volume must already be configured. Do not infer a valid login from a volume name.
Start the existing independent supervisor in its own terminal:

```powershell
python -m laomedo.host.leases.service_cli serve --state C:/LocalRuntime/laomedo/lease
```

The supervisor must outlive the runner. It is not a child of runner recovery.
Keep it running until owned work has ended and cleanup is confirmed.

## Start the app

Create a private host file `C:/LocalRuntime/laomedo/runner-service.json`:

```json
{
  "provider": "codex",
  "state": "C:/LocalRuntime/laomedo/runner",
  "skill_store": "C:/LocalRuntime/laomedo/registry",
  "source": "C:/Work/my-project",
  "lease_service": "C:/LocalRuntime/laomedo/lease",
  "port": 8765
}
```

If using an explicitly reviewed local rebuild, add `image_id` with its full
`sha256:` identity. Omitting it retains the normal historical image pin.
Neither graph fields nor browser requests can choose this identity.

From the prepared app environment, run one command (replace installation paths):

```powershell
laomedo-app --runner-config C:/LocalRuntime/laomedo/runner-service.json --frontend C:/LocalRuntime/laomedo/upstream-langflow/src/frontend/build --components C:/Work/laomedo/components --state C:/LocalRuntime/laomedo/langflow
```

The equivalent source entrypoint is
`python -m laomedo.integrations.langflow.launch.cli` with the same arguments.
The app binds to `127.0.0.1:7860`; `--port` changes the app port only. This command
explicitly selects the existing loopback auto-login mode. Do not expose it as a
hosted or multi-user installation.

Open the app and graph. New Codex nodes use the configured runner port on
`127.0.0.1`. Existing graphs keep their saved Runner URL; for a graph migrated
from a container app, check it against this installation's local runner address.
The app reads the runner's existing `state/api-token` file; no token is printed,
copied into a graph or required on the command line.

## Recover and verify

If the configured runner is offline and Docker is ready, the connection notice
offers **Start local runner**. Click it once. After the API is online, use
**Refresh models** or the Model dropdown's Refresh control. Starting the API and
loading its model list do not submit an Agent task or run the graph. Only a real
model list establishes successful discovery; a process-start acknowledgement
does not. Startup failures and unknown listeners retain their existing safe
recovery behavior.

PR and Skill service configuration is separate. Successful Codex discovery does
not establish that those nodes can discover resources or execute operations.

Stop the foreground app with Ctrl+C. The managed runner retains its existing
independent lifetime; closing the app does not kill it or active work. This
increment does not provide an automated installation-wide stop command. Preserve
runtime data and shut down only known owned services after work is reconciled.
