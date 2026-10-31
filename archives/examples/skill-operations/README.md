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
Agent provenance is asserted by the trusted Langflow component code, not
independently verified against runner records by the service. Edited graph code
can forge those assertions; the viewer labels this boundary. Real acceptance
must compare run references independently with the actual runner receipts.

Configure the independent loopback service with `python -m
laomedo.skills.operations.cli --registry PATH --database PATH --policies PATH
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

Open Skill files to see files above a Git-style commit graph in the left
navigation pane. Click any commit to compare the selected file from that
revision with its pinned current contents, including intervening changes.
The visual inline editor shows full current contents with historical changes
highlighted. Unchanged lines with equal old/current indexes use one number. Changed rows
and unchanged lines with shifted numbers show both index cells; missing indexes
are blank. A dedicated 24 px marker column renders
bold 18 px +/minus signs. A horizontal header rule and index divider separate
the compact columns. The visible rows are virtualized; Monaco computes changes.
Digit-sized index columns have a 4 px gap and thin divider. Revision hashes are
shortened, with the full identity on hover. No aggregate raw patch or
patch headers are displayed. Clicking another file retains the selected commit.
Historical-only files remain available to inspect deletions; absent sides are
empty and binary files show metadata. Current source exits comparison.
Drag the separator to resize navigation; arrow keys and Home/End also work.
No Files/History switch or additional Agent turn is needed. Parent and cumulative
patch endpoints remain read-only API records, separate from the visual editor.
The [earlier viewer evidence](viewer-evidence.json) is historical for fe2857b:
it verifies the replaced aggregate-patch interface, not the current visual editor.
File/history browsing never runs the graph. Ordinary reference-only graphs work
without an operations service. The journal is append-only through this API, but
local administrators can alter it; no signed audit or automatic pruning exists.
Interrupted attempts may leave unreferenced drafts/bundles, not partial history.
Operation Result reports failed before apply and conservatively unknown after
an apply transport failure; reconcile history rather than automatically retrying.

The [real verification evidence](evidence.json) records one original Docker Agent
turn that appended an instruction to the existing real `pr-feedback-title` skill
and added its operation-format reference, in one commit. Independent readback,
parent/current diff, source/canonical preservation, same-ticket replay and
container cleanup passed. The [executed graph](executed-flow.json) retains exact
embedded code; the [review graph](flow.json) selects the resulting candidate and
refreshes node code for later failure routing and exact-ID selection. It was not
rerun. See [prospective protocol and startup recovery](PROTOCOL.md).

The test runner/lease services stopped. A separate review service has no edit
policies; opening files/history or pressing Run there cannot start a paid turn.
The saved runner URL is an inactive ephemeral endpoint. Reconfigure trusted
services and authorize a new bounded campaign before another real execution.
Internal fixtures are not real integration acceptance. Native cancellation,
production ownership, multi-commit promotion and Git publication remain untested
or outside this campaign. User graph review and final CI/review remain pending.

### Agent control ownership migration

The current flow.json and builder now configure the Agent skill on a separate
Skill node connected to Skill References. The two-node feedback cycle remains;
its read-only Skill dependency is included in the isolated body. Request identity
is automatic. These updated exports were not executed against a model/provider.
The earlier flow is preserved in historical-flow-before-skill-input.json;
previous evidence describes that historical run, not execution of the migrated
export. No execution budget or ledger has been reset.


## Overview authoring

A complete summary appears above files/history between horizontal dividers,
without a frame. It uses the pinned `SKILL.md` description, with a prose fallback.
Clicking the summary row opens/closes the full description, initially collapsed;
the summary stays visible. Provide optional root
`OVERVIEW.md` for purpose, usage and workflow illustrations; otherwise the full
view renders SKILL.md without frontmatter. Local Markdown links and image paths
stay within the same immutable snapshot. PNG/JPEG/GIF/WebP and sanitized SVG
workflow diagrams are supported. Remote media and active markup are not loaded.
These documents/assets are ordinary versioned skill files and can be changed
atomically through the existing Skill operations. Opening the overview never calls a model or changes a revision. Historical comparisons keep the overview pinned to the current revision.


The [overview review graph](overview-flow.json) selects the real documentation
candidate described in [overview evidence](overview-evidence.json). It adds
OVERVIEW.md and assets/workflow.svg to the existing real Agent result through
one atomic **operator-authored** SkillOperations commit, not another Agent turn.
The exact purpose/usage documents are in [overview/](overview/OVERVIEW.md).
All existing bundle files and canonical latest remain unchanged. The original
Agent result graph and exact executed graph are preserved separately.

The temporary host documentation policy scoped writes to SKILL.md (required by
the existing policy schema), OVERVIEW.md and assets/workflow.svg; only the last
two changed. SVG is classified as script-capable by that schema, so its flag was
allowed for this exact vector-document path; no command execution or additional
script path was authorized. This policy is not installed in the read-only preview.

The internal [skill-summary](../../src/laomedo/skills/resources/skill-summary/SKILL.md) authoring skill
fills missing descriptions through ordinary versioned edits and preserves user
summaries. It is not invoked by opening the read-only viewer.

Host preparation adds the packaged internal summary skill to authoring tasks only
when the pinned SKILL.md description is missing or blank. Applying such a task
requires a nonempty description in the new revision. Existing descriptions do
not trigger summary generation; the read-only viewer never triggers an edit.
