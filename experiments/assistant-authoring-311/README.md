# Internal-assistant flow authoring acceptance (#311)

This is disposable experiment tooling on permanent `exp`, never a production
dependency. `inspect_metadata.py` runs the installed Langflow template builder
against the five exact audited adapters. The owner explicitly authorized this
configuration-code instantiation after an automatic review rejection. It does
not call refresh hooks, start MCP servers, authenticate providers or submit models.

Observed against implementation `037f6c256` on 2026-11-24: all five installed
templates matched their exact audited source digests and their named outputs.
The MCP adapter exposed `response` and `component_as_tool`. Zero model submissions.
This establishes metadata fidelity, not graph execution acceptance.

## Bounded live plan

Owner budget: at most six internal-chat submissions and two Agent-node runs.
Use the selected saved account through normal app/MCP and human approval routes.
Do not author target graphs through an API harness on the model's behalf. Preserve
exact saved revisions; no manual editor save between model save and execution.
No GitHub/repository writes, publication or new credential handling is authorized.

1. Fresh held-out deterministic text/template/output flow: agent discovers schemas,
   authors and saves, validates and proposes execution. Independently inspect the
   saved graph, approve through the app, compare execution revision and output.
2. Read actual output and edit/combine a new target from observed saved sources;
   verify untouched source graphs and exact typed ports, then approve deterministic run.
3. Diagnose a deliberately missing required input with metadata-only validation;
   repair, save and propose a new deterministic run. Require zero premature dispatch.
4. Configure an audited Agent using the explicitly selected account/model/effort;
   optionally connect an authorized pinned Skill or existing registered MCP only.
   Inspect actual binding metadata, approve one bounded Agent-node run.
5. Inspect that actual result; request a second owned Agent run and exercise exact
   graph cancellation while observing requested vs execution-owner settlement.
6. Reconcile outputs/status and summarize unsupported configuration honestly.

Zero-effect negative checks (no model submissions): changed revision, foreign owner,
   expired resolution, borrowed resolution, changed/disconnected account, changed
   registered MCP version, missing permissions and output-release revocation. Unit
   checks support these invariants; real owner-bound integration remains separate.

Keep a private ignored submission ledger before dispatch. Never put counters or
verification authorization gates in normal services. No private run transcripts,
credentials, browser cookies or runtime databases belong here. Publish only
sanitized aggregate outcomes tied to exact implementation/spec revisions.

Private GitHub node acceptance is gated on separate PR #287, not silently bypassed.
## Observations on 2026-11-25

Six internal-chat submissions have been used conservatively; four reached native
model turns and two failed before a turn (restart safeguard and a transient
Docker control failure with confirmed cleanup). No Agent-node run was submitted.
No further submission is authorized by this experiment's original budget.

The internal assistant built and saved a four-node deterministic concatenation
flow, reloaded/validated its exact saved revision and proposed execution. Existing
human approval executed it; `inspect_receipt.py` independently read the saved
graph, retained exact output `Order: plum / quantity 7` and four successful vertex
records belonging to that exact job. The assistant then read the actual output
and statuses through MCP and proposed a quantity-only edit. Approval preserved
the remaining graph; no editor configuration repair occurred. Prompt Template
hooks were explicitly unsupported and refused, rather than silently bypassed.

The live Agent probe exposed a native catalogue identity mismatch:
`ext:laomedo:LaomedoCodexAgent@extra` was classified by its registry key instead
of its template's canonical name. Corrected implementation `c0b21b0b9` preserves
the registry ID and exact-source digest gate. `inspect_loader.py` verifies the
five authorized templates through the real directory loader and the native pure
namespace decorator. It does not establish live initialized-catalogue dispatch.
`inspect_tool_receipt.py` examines only this experiment's exact synthetic message.

The later implementation `b7580611f` also preserves narrow verified browser
metadata for an automatically consented graph task. Concern-owned authority and
revocation tests pass; its final Claude implementation review hit quota and is
pending. Code through `c0b21b0b9` and AS311/proposal design through specs `587226d`
have independent review; the later technical spec paragraph `1ef4935` is pending.
Agent, Skill, registered MCP, cancellation, resource repair and holdout acceptance
remain incomplete. These aggregate observations do not make the feature ready
to merge. Raw transcripts, credentials and runtime databases remain untracked.
