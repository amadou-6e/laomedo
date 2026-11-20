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
