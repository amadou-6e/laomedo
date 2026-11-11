# Actual layout review captures, 11 November 2026

Production source cc02e68b8b65dfd13e65366196cc97f6ac6060af. Upstream frontend fec71dca901949c09ed4d63315804337cd2eb13d with current Laomedo overlay, freshly built using isolated Node22.22.0 (system Node20.11.1 was too old for Vite7). Actual Langflow/lfx1.12.3 app, fresh private SQLite/config/registry, loopback17875. Headless Edge, viewport1600x1300, fresh browser context. No model prompts or task execution.

The view-only graph uses existing Skill and Codex nodes copied from examples/langflow-workgraph-demo/flow.json, plus a second copy of the existing Codex node in resume mode. Only positions, second node identity, operation and a Run Reference -> Prior Run edge were composed for the visual exercise. No provider implementation or field schema was synthesized. The sanitized graph is retained alongside the actual screenshots.

Observed browser controls: Edit Request hidden; opening Advanced settings reveals Revision; connected Prior Run visible and edge retained. Full screenshots show default and Advanced states. Empty source yields No source found; no discovery-service or authenticated model-readiness acceptance is claimed. Local backend is intentionally not configured. Initial capture harness used an invalid output name run_reference/Data; corrected to the actual output run/JSON before these images. That failed harness observation is retained in local logs; no production change was required.

The initial unmodified workgraph-demo import also reported removal of an obsolete Output Requirements edge. This is not concealed as working execution acceptance; the view-only graph does not exercise that separate legacy example path.

VS Code integrated-browser opening remains unverified: available tooling exposes no command-execution bridge into the running editor. No user editor/profile was restarted or modified. The isolated preview can be opened directly from the final local URL. Headless capture is not a claim that the integrated browser was opened.

Reviewer status: actual default/Advanced GUI screenshots visually APPROVE in the same read-only Claude conversation; optional empty-source placeholder wording suggestion remains nonblocking. Current layout code/metadata and LC01 guard correction APPROVE, with declared import-order audit limits. These screenshots establish rendered controls only, not real agent execution, accessibility certification or owner final graph acceptance. Capture/server harness code APPROVE after full source and graph-handle inspection. Printed visibility checks are observations, not asserted controls; the visual verdict rests on the actual images.


Publication correction: the experiment-wide text attribute normalized the initial PNG blobs despite unchanged local captures. Scoped binary attributes plus explicit renormalization now preserve exact original screenshot bytes; both staged blobs were compared byte-for-byte with the captures before this correction was committed. Initial screenshot blobs at9477b4da should not be used.

