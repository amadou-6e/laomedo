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
