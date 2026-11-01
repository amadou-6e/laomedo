# Missing-summary real Agent verification

This new, user-authorized campaign creates and tests `skill-workspace-guide`.
Its source instructions are real guidance for the current Skill workspace;
the missing description is the actual authoring task. The user authorized
creating a new skill for this test. No fake provider or simulated Agent is used.

Use a new registry, journal, runner state and lease service, leaving previous
campaigns and ledgers untouched. Maximum one native model turn, no output
continuations and no automatic retries of uncertain dispatches. Use the existing
LaomedoCodexAgent, Docker LocalRunner and dedicated authorized login volume.
Never print credentials or copy unrelated host configuration.

The two-node graph sends the pinned source through Skill Task to the existing
Agent and returns its JSON proposal through the same Skill Operation input.
Host preparation detects the missing description and supplies the packaged
internal summary skill. Restrict the policy to editing SKILL.md. The Agent must
add only one description line, preserving every other byte. Apply through the
normal host service, record exact parent, diff and execution provenance, and
read back registry bytes independently. Canonical latest and the source remain
unchanged. Preparing an already-described candidate must not request generation.

Record all failures, exact source revision, actual run/thread/turn identity,
image digest and container cleanup. Do not call a failed or uncertain run a
success. Keep public evidence free of tickets, credentials and raw transcripts.
Stop the edit/runner services afterward; any viewer must have an empty policy map.


## User-approved additional turn

The first actual Agent turn completed and generated a grounded summary, but
returned extra `]}` after its JSON object. The host correctly refused it; the
registry has only the import commit and no accepted edit. Preserve the run and
its ledger. The user explicitly replied "Allow one additional turn" on
2026-10-18. Permit exactly one further turn (maximum total two), with output
continuations still disabled. Check the existing completed run, invalid JSON,
one attempted turn and zero applied results before starting it. Never erase
records or replace this failure with a success claim.


## Reviewed-prompt verification authorization

After both invalid JSON attempts, independent Claude review found conflicting
Agent/host output instructions. The implementation now sends only the internal
skill's Agent instructions, excludes YAML metadata and host integration prose,
and repeats the JSON-only operation contract last. Claude approved that prompt
fix in design; it has not yet established real acceptance.

On 2026-10-19 the user explicitly replied "Allow one verification turn". Permit
exactly one new native turn against the corrected prompt (maximum total three).
Before dispatch, verify the existing two completed invalid-JSON runs, ledger
count two, import-only history and zero applied results. Preserve both prior
runs and authorizations; never reset the ledger or silently retry a third turn.

The authorized third turn completed on 2026-10-19 but again returned trailing
`]}` after its operation JSON. The host refused it. Ledger: three attempted
turns, three requests, one import commit, zero applied results. No further turn
is authorized. All three native runs and the original source are preserved.

## Output-correction verification

On 2026-10-19 the user instructed ?fix and rerun? after clarification that the
example disabled output retries and omitted requirements. Connect pinned
action/message/files requirements and permit one same-thread output correction.
Run once, using at most two new native turns (campaign ceiling five). Preserve
the three prior refused runs and ledger; do not reset, silently restart, or
weaken host proposal validation. Correction is output-only, subject to existing
side-effect safety checks. All nested edits still require host validation.

The first correction-configured attempt consumed one turn but Langflow discarded
the DataInput template value: runner requirements were absent and no correction
ran. Preserve that fourth failed run. Fix static configuration using a validated
JSON input; verify the actual native-graph runner request offline before the
corrected rerun. Under the user's fix-and-rerun instruction, run one further
initial turn with at most one same-thread correction (campaign ceiling six).
Do not reset the existing four-turn ledger.

Result: the corrected run completed and host-applied the description-only edit.
It used one new turn (five total of ceiling six). Pinned requirements, native
precheck and final output validation were active; no correction was needed.
Independent readback, parent history and same-ticket replay passed. Both source
and canonical latest remained unchanged. No further run is planned.
