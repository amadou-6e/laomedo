# Skill operations

The existing Skill node accepts ordinary operations and direct feedback from
the original Codex Agent: **Skill Task → Agent Task → same Skill Operation**.
No new Agent component is introduced. `build_flow.py` exports without execution.

An operation replaces/adds/deletes multiple UTF-8 files in one validated batch:

```json
{
  "action": "modify",
  "message": "Clarify the output contract and document its fields",
  "files": [
    {"path": "SKILL.md", "content": "Complete replacement text..."},
    {"path": "references/operation-format.md", "content": "Complete reference text..."}
  ]
}
```

This schema example is illustrative, not a working or acceptance result. Null
content requests deletion; host policy must allow every changed path/type.
The model never supplies authorization, target, identity or provenance fields.
The host records a parent-linked commit, exact immutable tree, patch, timestamp,
message, changed paths, policy and adapter provenance. A revert has a distinct
commit even when its bytes match an older revision. It is registry history,
not a Git source commit or tamper-proof external audit trail.

Configure the independent loopback service with `python -m
laomedo.skill_operation_server --registry PATH --database PATH --policies PATH
--api-token-file PATH --port PORT`. Policies is a private JSON map from skill ID
to a validated existing edit policy. Backend-only environment variables are
`LAOMEDO_SKILL_OPERATION_URL` and `LAOMEDO_SKILL_OPERATION_TOKEN_FILE`. No token,
ticket or policy-authorizing input belongs in a saved flow. Registry and drafts
must be outside Git; protect the SQLite journal and registry as private state.

Each operation freezes a candidate and emits its Skill Reference and commit in
Operation Result. It never moves canonical latest. Promotion remains a separate
reviewed operation; multi-commit candidates need an explicit reviewed publication
against canonical latest. Existing source files and pinned flows retain old bytes.

For subsequent edits select the new exact revision and its Base Commit from
history. Empty Base Commit works only at the imported root. A fresh graph run is
a fresh operation; expired or uncertain replies must be reconciled, not blindly
rerun. Five-minute capabilities are backend-only and expire using wall and
monotonic clocks. Exact valid-ticket replay produces no extra commit.

Open Skill files → History to inspect paginated commits and per-commit diffs.
File/history browsing never runs the graph. Ordinary reference-only graphs work
without an operations service. The journal is append-only through this API, but
local administrators can alter it; no signed audit or automatic pruning exists.
Interrupted attempts may leave unreferenced drafts/bundles, not partial history.

See [prospective real verification protocol](PROTOCOL.md). Real acceptance and
the user-review graph are pending until evidence is recorded; internal unit
fixtures do not establish real Agent execution.
