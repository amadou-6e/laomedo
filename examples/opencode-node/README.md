# OpenCode graph node

The existing experimental OpenCode adapter now supports the current node lifecycle:
Fresh, nonblocking Start, Status, Resume and Cancel, with Answer, Run Reference
and Submission / Outcome outputs. It uses a separate isolated Docker controller
and the existing credential-free command worker, immutable skill store and bounded
turn ledger. The original Codex node remains unchanged.

The node follows the current Codex controls: Task and Operation, runner-backed
Provider/Model and Variant dropdowns, then Skill References. Technical settings
are under the collapsed Advanced controls section; legacy reference fields stay
hidden. Refresh discovers connected provider models without creating a session
or consuming a model turn. Only the default variant is supported.

Select an OpenCode node and choose Activity to open graph agent activity with that
node's newest captured invocation selected. The provider is identified as OpenCode
in the conversation and metadata. Opening Activity does not start an agent.

## Example

`build_flow.py` builds a native two-node Skill -> OpenCode graph from a real
existing immutable registry reference. It validates the actual Langflow ports;
it does not execute a model or supply fake provider results.

```text
python examples/opencode-node/build_flow.py --reference reference.json --model opencode-go/gpt-6-luna --runner-url http://127.0.0.1:18768
```

The reference file must contain the selected real `skill_id`, `revision_id` and
`tree_hash`. The saved example uses the same read-only project inspection skill
as the graph activity verification. The bounded verification workspace contains a byte-identical excerpt of the first
six lines of the real `examples/github-pr/README.md`, plus the pinned skill. Change the runner's source workspace when
using the node for other projects.

Install the whole Laomedo component category and runtime package. The OpenCode
component imports the Codex client lifecycle from that category. The runtime
must make both the runtime and component package paths available, as in the
existing experimental OpenCode deployment.

Existing saved Codex/OpenCode templates must be upgraded to the current component
to retain hidden saved run references during graph execution. The hidden
`run_reference_json` field must have `override_skip: true`; this fixes saved-JSON
Resume, Status and Cancel in both agent types. The local example is upgraded.

## Runtime and credentials

Use OpenCode 1.18.33 with a dedicated controller profile. Credentials stay in the
controller; command workers receive only workspace, canonical and registry mounts
and have no network. Pin both image identities. `worker_image_id` allows an
explicitly approved locally rebuilt worker identity and is part of the resume
binding, together with the controller identity and keyed credential binding (the raw fingerprint is not exported).
Set `LAOMEDO_OPENCODE_RUNNER_TOKEN_FILE` on the app host to the dedicated runner's
transport token file. This is separate from the Codex runner token.

The isolated runner requires a selected provider/model and currently verifies only
the `default` variant. Unsupported variants and output requirements are refused
before dispatch. Output Contract/precheck inputs and the Codex join bridge are
not exposed on this node. This change does not extend the Codex-specific PR/Skill
feedback loops to other providers.

## Activity evidence

Capture is opt-in through `LAOMEDO_AGENT_ACTIVITY_DB`, as for Codex. Each accepted
attempt has separate receipt boundaries. Resume captures new message IDs only;
it does not charge the previous conversation again. Native messages and tool
parts remain available in the source/metadata controls.

This first adapter captures native HTTP message snapshots at turn completion,
not the OpenCode SSE stream. The UI therefore marks stream capture partial and
shows a snapshot-only note. Native timestamps drive turn/tool timing. Subagent
sessions and OpenTelemetry exporters are not captured by this path.

Token counts aggregate unique native assistant messages for the current attempt.
Cached input is included in total input, and reasoning in total output. Monetary
estimates remain unknown for provider-qualified models without a verified price
entry. Native reported costs remain in source metadata; they are not treated as
Go subscription charges or account credit consumption.

## Verification status

Internal tests cover lifecycle identity, before-dispatch cancellation, resume
receipt isolation, malformed input and native snapshot projection. These fixtures
are not integration acceptance. Real fresh and resume graph runs completed on 2026-10-22 using OpenCode 1.18.33
and OpenCode Go (`opencode-go/gpt-6-luna`) in the dedicated Docker runner. Both
used the same native session; the separate ledger reached exactly 2/2 turns. The
fresh run loaded the pinned skill and read the approved six-line README excerpt
through the isolated command worker. Resume reused the session without tools.
The Activity viewer showed separate graph invocations, native conversation and
per-attempt token usage. This verifies the bounded fresh/resume path, not live
active cancellation, SSE/OTLP or subagents. The older prototype ledger and its
historical evidence are preserved. Active cancellation must not be inferred
from an abort acknowledgement alone.
