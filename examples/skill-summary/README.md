# Missing-summary authoring

Normal authorized Skill preparation adds the packaged internal
[summary skill](../../laomedo/resources/skills/skill-summary/SKILL.md) when the
pinned SKILL.md description is absent or blank. The existing Agent receives
those instructions alongside the requested edit. Applying the operation must
leave a nonempty description; the ordinary immutable journal records any
accepted edit. Existing descriptions, including multiline descriptions, do not
trigger generation. Reads, discovery and import do not dispatch models.

The [new workspace-guide skill](source-skill/SKILL.md) was created for the real
test at the user's request. Its missing description is the actual authoring
task. [Protocol](PROTOCOL.md) records the initial one-turn bound and the user's
explicit authorization for one additional turn.

## Real verification: incomplete

Both actual LaomedoCodexAgent/Docker LocalRunner turns completed and authored a
grounded description, but each appended `]}` after its complete operation JSON.
The strict host parser refused both answers. There is no accepted candidate
revision or successful end-to-end generation claim. The original source and
canonical registry revision remain unchanged; both containers were cleaned and
the edit/runner services stopped. No more model turns are authorized.

[Evidence](evidence.json) retains the two run identities, unapplied descriptions,
failure reason, ledger count and journal counts. [Executed graph](executed-flow.json)
is the second actual attempt, not a successful review graph. Internal unit tests
verify preparation, refusal and revision history mechanics; they do not replace
this missing real integration acceptance.
