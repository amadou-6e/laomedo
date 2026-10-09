# Phase F: no-model prepared-state UI setup

The disposable pinned Langflow server imported the five-node flow in
`start` mode, opened the visible Playground, and found the local runner ready.
It did not click Send, reserve a shared ledger entry, start a native worker or
submit a model turn. The saved flow's embedded Codex Agent and Skill code
matched the pinned component files. The disposable UI container was absent at
teardown, and the runner had no run records.

Private state: `%LOCALAPPDATA%/Laomedo/exp22-phase-f-preflight-01/`.

| Private sanitized artifact | SHA-256 |
| --- | --- |
| `sanitized.json` | `e195b1ec6520660683c681be4f767e927817194930a617fadbb4f4fcaeefb343` |
| `teardown.json` | `775a6defe9e4cd1ef350bdc2f61ad68ec487eb5667589b4f7d7399b4c5efe954` |

This setup check does not prove the acknowledgement hold, browser Stop
propagation or absence of a native turn. The actual prepared-state case must
be judged from its separate ledger entry, exact route audit and runner record.
