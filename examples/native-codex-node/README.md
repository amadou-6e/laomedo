# Native Codex node example

`flow.json` connects Chat Input to the operator-installed Laomedo Codex Agent
and both its Answer and Run Reference ports to separate Chat Outputs. Both
branches share a single runner invocation. It pins the existing synthetic whole
skill fixture from `../skill-agent-pilot/skill/`; it contains no credential.

Install the component using [the component guide](../../components/README.md).
`compose.yaml` is the reviewable acceptance-server draft: localhost:7862,
read-only component mount, a separate data volume, and local auto-login enabled.
It leaves the existing localhost:7861 deployment alone. Start it only after
operator approval of that configuration.
Run `build_flow.py` inside the pinned Langflow 1.12.3 image with this repo available;
it validates directory discovery, rebuilds the component schema, and constructs
the four-vertex graph without a model call.

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

No real model turn has been run for this component yet. Existing pilot evidence
does not establish this node's installed-server execution. Freeze implementation,
spec, image, skill and permissions pins before a separately authorized run.

1. Verify the installed server catalog contains the category and component, then
   import/export/reimport the flow through its API.
2. Run a task requiring an observed skill read and fixture read, write/read a unique
   marker, and retain the returned reference plus private native command events.
3. Restart the runner and resume through the imported node, checking the same
   thread and exact prior snapshot and reading the marker.
4. Start an independent fresh run and verify the marker is absent.
5. If the approved cap permits, run an interruptible tool task and cancel using a
   known runner ID; verify terminal cancellation and retained partial events.

Use a separate ledger with at most four submitted turns only after approval;
timeouts consume turns. Credential-free rejection tests run first. Never reset
the historical pilot ledger or make another auth copy. A test that does not fit
the approved cap remains unverified. UI Stop propagation is deferred to
[issue #22](https://github.com/amadou-6e/laomedo/issues/22).
