# Native Codex node example

`flow.json` connects a separate Laomedo Skill node and Chat Input to the operator-installed Laomedo Codex Agent
and both its Answer and Run Reference ports to separate Chat Outputs. Both
branches share a single runner invocation. It pins the existing synthetic whole
skill fixture from `../skill-agent-pilot/skill/`; it contains no credential.

The five-node example is a follow-up to the original four-node acceptance flow.
Historical six-turn evidence describes that original version. The connected Skill
node has separate synthetic graph verification and a real seventh-turn result in
[skill-node-evidence.json](skill-node-evidence.json). Historical evidence alone
does not prove new wiring. `verify_skill_node.py --approved-model-turn` reproduces
the installed-flow test using one separately authorized turn; it refuses dispatch
without the flag. Private responses stay outside Git. The installed example uses
runner port 8766; the exported runner URL is configurable.
The seventh-turn evidence shows that the wired reference reached the runner and
the run completed with one native command result. It does not show a read of the
skill body or compliance with its instructions; skill use remains `offered`.

Install the component using [the component guide](../../components/README.md).
`compose.yaml` is the reviewable acceptance-server draft: localhost:7862,
read-only component mount, a separate data volume, auto-login disabled, and a
read-only mount of the runner's private `api-token` file. Set
`LAOMEDO_RUNNER_TOKEN_PATH` to that file outside Git before starting Compose.
The token is never stored in the flow or mounted into agent command workers.
With auto-login disabled, provide a private `LANGFLOW_ACCESS_TOKEN` to the
acceptance harness and optionally `LANGFLOW_API_KEY`; the harness keeps these
in memory and outside Git. The earlier acceptance run used auto-login before
this draft was tightened, so its historical evidence is not a test of the new
login setting.
It leaves the existing localhost:7861 deployment alone. Start it only after
operator approval of that configuration.
Run `build_flow.py` inside the pinned Langflow 1.12.3 image with this repo available;
it validates directory discovery, rebuilds the component schema, and constructs
the five-vertex graph without a model call.

Import `flow.json` into an approved local acceptance server. Set advanced Runner
URL if its runner uses a different loopback port. Trigger through the editor or
Langflow run API with a task. Read the Run Reference output for native thread,
snapshot hash, opaque artifacts and raw-event references.

For a later resume, choose resume and connect the prior Data output, or supply
the returned object as advanced Prior Run JSON through the editor/API tweaks.
Keep model and effort identical. Restart the runner before the acceptance resume
to demonstrate persistence. Missing snapshot or mismatched identity must fail,
not silently create a new run. Status and cancel use only the prior run ID.

## Prospective #21 acceptance

Six authorized model turns have now been submitted through the installed server.
See [sanitized evidence](evidence.json): catalog/round trip, fresh execution,
restart/resume, independent fresh tool/host checks and explicit cancellation
status. The historical evidence did not verify container termination at the
moment of cancellation. The revised runner now forces named-container removal;
a separate no-model Docker probe verified this cleanup path.
The failed third task and inconclusive fourth cancellation attempt remain recorded.
The user extended the cap from four to six without resetting the ledger. It is now
6/6; another model turn requires new authorization, not an implicit retry.

The following prospective sequence remains the reproduction plan. Freeze
implementation, spec, image, skill and permissions pins before a new attempt.

1. Verify the installed server catalog contains the category and component, then
   import/export/reimport the flow through its API.
2. Run a task requiring an observed skill read and fixture read, write/read a unique
   marker, and retain the returned reference plus private native command events.
3. Restart the runner and resume through the imported node, checking the same
   thread and exact prior snapshot and reading the marker.
4. Start an independent fresh run and verify the marker is absent.
5. If the approved cap permits, run an interruptible tool task and cancel using a
   known runner ID; verify terminal cancellation and retained partial events.

Use a separate ledger with an explicitly approved submitted-turn cap;
timeouts consume turns. Credential-free rejection tests run first. Never reset
the historical pilot ledger or make another auth copy. A test that does not fit
the approved cap remains unverified. UI Stop propagation is deferred to
[issue #22](https://github.com/amadou-6e/laomedo/issues/22).

The `acceptance.py` harness uses the approved localhost:7862 server and localhost:8766
runner. Run prepare (installed catalog and flow round trip) and preflight first.
Then explicitly run first, resume after restarting the runner, fresh, and cancel,
each with `--approved-model-turn` only after bounded authorization. It never starts
servers or resets ledgers. Raw responses stay in the private native-node-21 state
outside Git; only sanitized summaries are suitable for publication. The cancel
phase invokes the node's explicit cancel operation after an observed sleep command,
using a known run ID from private runner records; it does not claim UI Stop support.
The corrected command-start trigger passed in turn five. The historical explicit
cancellation used the runner's flag and app-server client teardown; native
interrupt and immediate container termination were not verified. Thirty-three
partial events remain, the interrupted Langflow run returned HTTP 500, and no
Codex containers remained at the end of the acceptance sequence. The current
runner sends `turn/interrupt` and checks named-container removal, but that model
turn was not repeated. UI Stop propagation is still separate follow-up.
Windows trace reading requires UTF-8. Resume validates the input snapshot; its
output hash may legitimately change, as it did when an empty `.aws` directory
appeared. The private trace's recorded command executions did not mention `.aws`;
the exact creator is unknown, so this is not treated as an agent-requested edit.
Track outstanding command semantics in
[issue #24](https://github.com/amadou-6e/laomedo/issues/24).
