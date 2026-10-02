# Local Langflow skill-agent pilot

This example covers Laomedo issues #8 through #11. The runner is a local,
single-user prototype. It reuses the Docker boundary from the #146 proof:
`laomedo-codex-boundary:0.159.2` at image ID
`sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`,
Codex CLI `0.159.2`, the existing `laomedo-122-docker-auth` volume, and
`runner-config.toml` at SHA-256
`a14cd7e8abb4216b16d29e55809c2c3c9a9c33cc0196fd459fc033aaaa1ea4c4`.
The Docker grant and mounts have not changed. No credential is in this example.

The [2026-10-01 evidence](pilot-evidence.md) records a successful real run
through the imported Langflow flow, native thread resume after runner restart,
fresh-run independence, missing-snapshot rejection, and cancellation status.
The historical cancelled turn did not verify that its container stopped. The
current runner performs named-container cleanup; a no-model Docker probe
verified teardown, but that historical model turn was not repeated. The
authorized ledger reached 4/4. AGENTVIZ inspection is deferred. Resume was
tested through the runner API; this saved Langflow component starts fresh runs.

The skill is pinned to revision
`sha256:a12c212a57a9bc8fa3f0ecd834c09f9576a37ee89e21c62a096b1213fcc2bef8`.
The source workspace contains only `fixture.txt`. A fresh run copies it to a
private workspace, materializes the exact whole-skill bundle under
`.agents/skills/laomedo-pilot`, and hashes both workspaces. A resumed turn
requires the native thread ID and last post-run hash. Missing or changed
snapshots fail before dispatch. `skill_use_evidence` remains `offered` unless a
native read or invocation event proves more.

## Local setup

Run from the Laomedo repository root. Python 3.10+ and Docker Desktop with
the existing private volume and pinned image are required. The store and run
state must be outside every Git working tree. The following locations are
examples under the current user's private application data directory:

```powershell
$pilot = Join-Path $env:LOCALAPPDATA 'Laomedo'
$store = Join-Path $pilot 'pilot-skills'
$state = Join-Path $pilot 'pilot-runner'
python -c "from pathlib import Path; import sys; from laomedo.skill_store import SkillStore; print(SkillStore(Path(sys.argv[1])).import_skill('laomedo-pilot', Path(sys.argv[2]))['revision_id'])" $store examples/skill-agent-pilot/skill
python -m laomedo.local_runner --state $state --skill-store $store --source-workspace examples/skill-agent-pilot/source --preflight
```

The import is a one-time operation. A second import of the same skill ID is
rejected; use `SkillStore.revision('laomedo-pilot', pinned_revision)` to check
an existing store. Preflight initializes the real Docker app-server and lists
model/effort options without submitting a turn. The runner defaults to a
**zero-turn cap**. Start it only with an explicitly authorized turn cap:

```powershell
python -m laomedo.local_runner --state $state --skill-store $store --source-workspace examples/skill-agent-pilot/source --max-model-turns 4
```

The cap lives in `turn-ledger.json` outside Git. Reservations occur before
`turn/start` and persist across runner restarts. Timeouts and rejected turn
submissions count. The HTTP API binds to `127.0.0.1:8765` only and every request
requires the private bearer token saved at `$state/api-token`. The Langflow
container needs that file mounted read-only at
`/run/secrets/laomedo-runner-token`; the token is read at call time and is not
stored in the flow export. Never mount the token into an agent command worker.
Write requests require `Content-Type: application/json`. The endpoints are
`POST /v1/runs`,
`GET /v1/runs/{run_id}`,
`POST /v1/runs/{run_id}/cancel`, and `POST /v1/runs/{run_id}/resume`.
An accepted cancellation returns HTTP 202; the original run request returns
HTTP 502 with status `cancelled` and its retained partial events.
The resume body needs `task`, `expected_post_run_hash`, `expected_thread_id`,
`model`, and `effort`. Results contain opaque output and raw-event references,
not private filesystem paths. Failed and timed-out requests return HTTP 502
with a run ID and error category. The status endpoint remains queryable.

After a completed run, export only its matching native Codex rollout for local
AGENTVIZ inspection:

```powershell
python -m laomedo.rollout_export --state $state --run-id '<run-id>'
```

This reads the existing Docker volume read-only, matches the native thread ID
under its `sessions` directory, and writes one JSONL file beneath the private
run directory. It never copies `auth.json`. Use the existing
`experiments/feasibility/123/probe_agentviz_import.mjs` against that private
file and a local AGENTVIZ parser bundle. Review its structural counts and
call/result IDs before sharing any report; do not commit the rollout.

## Langflow handoff

`pilot-flow.json` was generated from Langflow 1.12.3's own component schemas
with `build_flow.py`. The pinned image is
`langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0`.
The saved flow has Chat Input, a small Laomedo component, and Chat Output.
Its export contains the skill ID and revision, model and effort, and a fixed
`host.docker.internal` local endpoint. It contains no credential, raw skill
body, or private runner path.

The [built-in API Request component](https://docs.langflow.org/api-request)
was checked first. In Langflow 1.12.3 it
returns a normal `Data` value even for connection errors, including a synthetic
`status_code: 500`; it does not fail the flow. The small component in
`langflow_component.py` sends the same JSON request but raises a Langflow error
with the Laomedo run ID and error category for a failed agent run. A successful
result has structured `answer`, `run_id`, `thread_id`, `status`,
`skill_revision`, `skill_use_evidence`, `trace_ref`, and `usage: unknown` fields.
`usage: unknown` is deliberate: Langflow's outer token count does not measure
Codex's internal usage.

Import `pilot-flow.json` in Langflow's flow UI or
[`/api/v1/flows/upload/`](https://docs.langflow.org/concepts-flows-import).
The Langflow container must reach the host runner through
`http://host.docker.internal:8765`; Docker Desktop connectivity was checked
with a one-file loopback fixture. On Linux, `host.docker.internal` needs an
explicit host-gateway mapping, and a host listener bound only to `127.0.0.1`
will not be reachable through that mapping. The tested route is Docker Desktop.
Stopping a Langflow request or reaching the client timeout does not itself
cancel a runner run; query its status or call the runner's cancel endpoint.
Trigger the imported flow in the UI or via
`POST /api/v1/run/{flow_id}` with an `input_value` task. The imported flow ID
may differ from the export ID. An end-to-end evidence matrix belongs in
`pilot-evidence.md`; it must distinguish observed events from inferred skill
use and unknown usage.

The bundled API helper imports without submitting a model turn. Its `run`
operation does submit one and requires a private report path outside Git:

```powershell
python examples/skill-agent-pilot/langflow_api.py import --base http://127.0.0.1:7861
python examples/skill-agent-pilot/langflow_api.py run --base http://127.0.0.1:7861 --flow-id '<imported-flow-id>' --task 'Read fixture.txt with a shell tool, report its color and count, and write pilot-marker.txt with FIRST-RUN.' --private-report (Join-Path $state 'langflow-first-run.json')
```

The helper reads an optional `LANGFLOW_API_KEY` from the process environment
and never writes that key to the flow or report. The run API response is kept
private because it can include the task and answer.

Langflow 1.12.3 requires authentication for flow creation and an API key for the
run endpoint, including when the disposable server uses `LANGFLOW_AUTO_LOGIN=true`.
Create a key in the local Langflow server and supply it through
`LANGFLOW_API_KEY` when using the helper. This key authenticates to Langflow;
Codex continues to use the existing private Docker login. The observed test
used `/api/v1/auto_login` and `/api/v1/api_key/` with tokens held in memory.

To reproduce the model checks with a newly authorized budget:

1. Import the saved flow and invoke it with the first-run task above. Confirm
   the real trace contains completed command events and that the private
   workspace contains `pilot-marker.txt` with `FIRST-RUN`.
2. Read `GET /v1/runs/{run_id}`, restart the host runner with the same private
   state and cumulative cap, and post to `/v1/runs/{run_id}/resume` with that
   record's `expected_post_run_hash`, `expected_thread_id`, model and effort.
   Ask the agent to read the marker without changing files. Confirm the same
   native thread and unchanged snapshot hash.
3. Invoke the saved Langflow flow again, asking it to test for the marker and
   read the fixture without writing files. Verify a new thread and absent marker.
4. Invoke the flow with a shell task that reads the fixture and sleeps for 60
   seconds. After observing the command's native start event, post to
   `/v1/runs/{run_id}/cancel`. Check the retained partial events and Langflow's
   error containing that run ID and `cancelled`.

The missing-snapshot check temporarily holds the completed run's `post-run`
directory, attempts a resume with its original binding, then restores the
directory. It must return `post_run_snapshot_mismatch` before reserving a turn.
Once the ledger is exhausted, a new request must return
`model_turn_cap_reached` without issuing a native thread or changing the ledger.

## Credential-free checks

```powershell
python -m unittest discover -s tests -p 'test_*.py' -q
```

These credential-free tests cover exact materialization, workspace separation, snapshot
integrity, restart/resume binding, HTTP result and failure behavior, and the
persistent turn cap with a fake app-server. They do not establish a successful
model-backed Langflow run by themselves or a broader security boundary. Private raw events
remain under the runner state directory and are never committed.
