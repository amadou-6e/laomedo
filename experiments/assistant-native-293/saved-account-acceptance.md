# Saved-account chat acceptance

Production source: `93f2550b` on `feat/293`. Normal local-profile preview, separate runtime, same stable integrated-browser tab. No copied credentials or host-token injection. The owner completed the provider OAuth flow.

## Observed 2026-11-20

- Settings reported the saved Codex connection as connected.
- Initial inspection found chat reading the unused Zustand userData slot. Corrected it to the application AuthContext, then all 62 frontend tests passed and Vite built successfully.
- After restarting the owned preview and reloading the same tab, chat listed the account and loaded the actual model choices. Account selection remained explicit.
- Fresh `/status` completed without a model prompt and displayed the actual native thread and configuration.
- Sending the first ordinary message to that status-only thread failed before a model turn; cleanup was confirmed. An offline network-disabled native `thread/resume` against that exact acceptance thread returned error -32600 with a no-rollout category. No model prompt was submitted by the diagnostic. Native 0.159.2 does not persist that zero-turn thread. Related upstream report: https://github.com/openai/codex/issues/42099 . This path is NOT accepted.
- Separate normal fresh chat returned the requested acceptance marker.
- Its follow-up returned that marker from conversation context.
- With the owner explicitly approving the metadata transfer, a further follow-up called the real Laomedo MCP `list_workflows` tool and reported zero saved workflows for this isolated profile. No graph was changed or run.
- CoBrowse page reads and screenshot verified rendered native status and chat responses. This is implementer inspection, not independent visual review.

## Limits

No claim of initial-status resume acceptance, account disconnect acceptance, Claude/OpenCode live acceptance, independent visual approval, or merge readiness. Reviewer corrections and the new AuthContext fix await recheck. Full substantive review remains required. No private account IDs, credentials, or runtime files are retained here.

## Corrected zero-turn retention acceptance, 2026-11-20

Production source: `262221b6`, with later `ff75367a` CLI-finalizer and error-mapping changes outside these successful native executions. Corrective cleanup source `2415619c` has fixture verification pending focused reviewer recheck; it was not the source of these live runs.

- The owner selected retaining the real native controller, not restricting first status or submitting a hidden turn.
- Flow A: real initial `/status`, first ordinary marker reply, then contextual MCP follow-up. The real `list_workflows` call returned zero workflows and the answer recalled `LIVE-ZERO-TURN-293`. All three used the original status thread. Selected receipt audit: two model turns, one control receipt, materialized history, confirmed controller cleanup and verified Docker cleanup.
- Flow B: real initial `/status`, then the first ordinary message directly called `list_workflows`. Result: zero workflows and `FIRST-TURN-MCP-293`. Both used the original native thread. Selected receipt audit: one model turn, one control receipt, materialized history and confirmed/verified cleanup. This exercises reactivation of the original inactive endpoint under the new message authority.
- Idle cancellation: a completed status-only session closed its retained controller with zero model turns and confirmed cleanup.
- Idle conversation deletion: created a separate disposable status-only chat, observed native status, then deleted only that chat through the integrated-browser confirmation. Selected native receipt audit: status remained completed, live session closed, controller cleanup confirmed, zero model turns, Docker cleanup verified.
- The stable shared CoBrowse tab was restored to Flow B; a fresh screenshot showed status, the first prompt, actual MCP tool result and final answer. This is implementer visual inspection, not independent visual review.

The earlier failure above remains valid evidence for source `93f2550b`; the corrected path does not close and attempt disk resume of an unmaterialized thread. No graph was modified or run. No private account IDs, credentials, raw runtime state or personal transcripts are archived.

Limits: account disconnect/logout, real credential rotation, graceful shutdown and native-failure live acceptance remain unperformed. A changed launch token is intentionally refused because native process environment credentials cannot be replaced in place; a new conversation is then required. Full substantive reviewer status remains REVISE pending the focused recheck at `2415619c`; no merge readiness or independent visual approval claimed.

## Native command-backed bearer wiring, 2026-11-20

Production refresh source: `856c7ecfc`, registered commands4 image. The actual pinned Codex 0.159.2 binary ran in a disposable container with external networking disabled and a loopback fake Responses server. `native_bearer_rotation.py` opens one native thread with command-backed auth, changes the private token file before the first turn, then changes it again before a second turn on that same thread. Both native turns completed; the fake server observed exactly the expected renewed bearer for each request. Result: same_thread=true, native_turns_completed=2, renewed_bearer_used=true, requests=2, external_network=false, real_model_calls=0. No real credentials were involved.

This is native-binary protocol acceptance against a fake API, not real OAuth or model integration acceptance. Real saved-account OAuth rotation remains blocked by the shared integrated-browser tab reporting page_loading after preview restart. The server responds, but HTTP success is not rendered verification; owner reload has been requested. The reviewer approved the selected specification at b23032a and left implementation INCOMPLETE pending native wiring proof and corrective cleanup/recovery tests. Later tmpfs and recovery-copy corrections remain recheck pending.
