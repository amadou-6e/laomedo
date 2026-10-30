# Agent example migration and immutable history

The six executed Claude/Skill exports listed below are historical evidence. They
are restored at their ORIGINAL paths, byte-for-byte from Git baseline
`8e2a2925c74748672f3028ba09359c49b13e1635`, and excluded from in-place migration.
Use the current template shown in the table for new work. Existing run references
in the historical exports are observations, not current Resume acceptance.

The `github-pr/original-agent/flow.json` path was already a migrated, unexecuted
template at this baseline: its README explicitly records that distinction. It
remains a current template, with an additional exact baseline copy alongside it.
The older `historical-flow-before-skill-input.json` remains untouched.

| Historical original | Current template |
| --- | --- |
| `examples/claude-agent/activity-flow.json` | `examples/claude-agent/current-template-flow.json` |
| `examples/claude-agent/executed-flow.json` | `examples/claude-agent/current-template-flow.json` |
| `examples/claude-agent/first-executed-flow.json` | `examples/claude-agent/current-template-flow.json` |
| `examples/claude-agent/no-skill-flow.json` | `examples/claude-agent/current-template-flow.json` |
| `examples/skill-operations/executed-flow.json` | `examples/skill-operations/flow.json` |
| `examples/skill-summary/executed-flow.json` | `examples/skill-summary/flow.json` |
| `examples/github-pr/original-agent/historical-flow-before-agent-module-refactor.json` | `examples/github-pr/original-agent/flow.json` |

`agent-module-history.json` records SHA-256 and original Git object identity. The
migration CLI refuses these immutable paths; migrate an explicitly named copy.
Historical copies must not be automatically selected as current examples.

Owned CURRENT templates were explicitly regenerated for pinned Langflow/LFX
definitions and derived cache hashes. This is distinct from offline migration:
unchanged code never permits hash repair; changed code with a stale or unknown
original hash requires manual work. External/historical graphs are not silently
regenerated. Actual stale baseline code/hash pairs are retained as internal
regression controls. No current template or old run is live refactor acceptance;
new installed-wheel graph evidence is recorded separately.
