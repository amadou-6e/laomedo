# Missing-summary authoring

Normal authorized Skill preparation adds the packaged internal
[summary skill](../../laomedo/resources/skills/skill-summary/SKILL.md) when the
pinned SKILL.md description is absent or blank. The existing Agent receives
those instructions alongside the requested edit. Applying the operation must
leave a nonempty description (older files without frontmatter must add valid
frontmatter before an edit can be accepted); the ordinary immutable journal records any
accepted edit. Existing descriptions, including multiline descriptions, do not
trigger generation. Reads, discovery and import do not dispatch models.

The [new workspace-guide skill](source-skill/SKILL.md) was created for the real
test at the user's request. Its missing description is the actual authoring
task. [Protocol](PROTOCOL.md) records the initial one-turn bound and the user's
explicit authorizations and the later fix-and-rerun instruction.

## Real verification: passed

The corrected two-node Skill -> real LaomedoCodexAgent -> same Skill Operation
flow produced an accepted candidate revision. Only one description line was
added to SKILL.md. The host recorded its parent commit and backend Agent
provenance; independent registry readback and same-ticket replay succeeded.
Canonical latest and source files remain unchanged.

The Agent has a pinned action/message/files output contract and one permitted
same-session correction (`output_retries: 1`). The contract reaches the runner
through the advanced **Output Requirements JSON** setting because Langflow
ignores an unconnected static DataInput value. Connected requirements remain
supported; malformed pins or conflicting values are refused. The generic
contract checks the outer form; host policy still validates every file edit.

The successful run used one turn: precheck and final output validation passed,
so no correction was needed. This verifies the real authoring workflow and
contract binding, not a live correction being exercised. Five campaign turns
were used, with all four failed prior runs preserved. The first three had
trailing punctuation; the fourth exposed the discarded static DataInput value.
No parser repair, ledger reset or fixture provider was used.

[Evidence](evidence.json) records the actual candidate, parent, diff, execution
identity, validation and prior failures. [Executed graph](executed-flow.json)
is the successful invocation; [review graph](flow.json) selects its candidate
with the edit request cleared. [Generated skill](generated-skill/SKILL.md)
contains the exact accepted bytes. The runner and edit services are stopped;
the separate preview has an empty edit-policy map.
