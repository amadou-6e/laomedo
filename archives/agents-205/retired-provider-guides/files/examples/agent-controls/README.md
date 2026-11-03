# Agent node advanced controls

Open the Agent in the existing real Skill/Agent review graph. Advanced controls
starts collapsed directly inside the node; expand to edit technical settings.
Main Model, Reasoning Effort and existing Operation remain visible. Collapse
preserves values. Inspector-promoted fields stay in the main form. Ports and
execution behavior are unchanged.

[evidence.json](evidence.json) records the production build, five internal tests,
Claude review and real Edge verification of the original Agent component:
inline expansion, value retention, keyboard toggle, stable ports, original
preview timeout restored and checked after reload, zero browser errors and zero
execution requests. No model turn ran; this does not claim new provider or
mutation acceptance. OpenCode uses the same renderer but only its selector was
unit-tested in this slice.

Implementation and specifications are isolated on feat/agent-node-controls.
No merge is authorized until the user reviews the working graph and approves.

## Request identity and Skill ownership

Request ID is automatically assigned during execution. Request ID, Skill ID and
Skill Revision are not Agent controls; stale imported overrides are ignored.
Fresh/start requires Skill References from a Skill node. Inline-only older flows
must add that connection. The current PR/Skill example exports and builders were
migrated; exact prior exports are retained as historical evidence.

[ownership-evidence.json](ownership-evidence.json) supersedes the earlier controls
UI proof. It records46componenttests,26nativefeedbackcontrols,5Reacttests,
production build and a real-registry browser check with no execution requests or
additional Agent turn. The migrated provider workflow was not rerun. Independent
Skill dependencies resolve twice in the bounded executor, which can read linked
sources twice; this accepted limitation is recorded in the contract. The branch
remains unmerged pending user review.

## Current model and reasoning controls

Model and Reasoning Effort are native dropdowns populated from authenticated runner model metadata. Refresh Model to load choices; selecting another model preserves compatible effort and clears incompatible effort. There is no fixed model/effort table or default. Discovery is serialized, cached for 30 seconds, and bounded; offline component upgrades preserve saved selections. Metadata discovery does not prove account entitlement or provider execution.

Skill References follows Reasoning Effort. Output Requirements, its JSON alternative, Prior Run, and Join Bridge URL are internal compatibility fields, hidden from the node. Configure the bridge centrally with LAOMEDO_BRIDGE_URL. Legacy serialized bridge values remain a fallback; an explicitly configured environment value takes precedence.

The earlier dropdown-evidence.json describes the historical fixed-table implementation, not current discovery. See [runtime capability audit](runtime-capabilities-audit.md) for remaining assumptions and [real Skill edit](real-skill-edit-evidence.json) for the successful original-Agent run. That real run predates develop integration and is not final-head provider acceptance. User reviewed the updated graph and approved merging on 2026-10-19.
