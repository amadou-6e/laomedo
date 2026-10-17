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
