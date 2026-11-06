# Manual Skill workspace

Open Skill files on a selected Skill node. The header keeps the Skill name and
short revision together; Graph pins identifies a differing saved graph reference.
When local editing permission is granted, text editing is always available.
The host configures edit and publish grants separately; the browser cannot grant
itself authority. See the [service walkthrough](walkthrough.md).

## Working copy and publication

Text changes, imports, renames, moves and deletions form one working copy. The
bottom-right Publish and Discard controls appear only when there are changes.
Publish validates the entire batch, records a candidate commit and promotes that
exact candidate to the registry. It does not publish to Git, change graph pins,
start an Agent or run a graph. The commit message is optional.

The publication summary lists every changed path, including saved unpublished
commits. Selecting a path opens its cumulative diff against registry current.
An unexpected newer registry revision refuses publication rather than silently
rebasing or overwriting its files. Candidate history and working text remain
available; divergent journals need maintainer-led reconciliation.

An uncertain response retains the exact request. Check result reconciles that
request; it does not create another save. Definitive validation failures preserve
working text for correction. A completed receipt can be read after permission
revocation without authorizing another write.

Discard opens a confirmation popup. Keep editing preserves the working copy;
Discard changes reloads saved files. Closing a dirty workspace uses the same
confirmation. No persistent browser draft recovery is promised after a crash.

## Files and history

Use [file actions](explorer.md) for text and binary assets. Empty working folders
remain visible after their last file moves or is deleted. They stay local: the
registry and commit diff describe files, not empty directories.

The [commit tree](navigation-verification.md) compares the selected file with the
current working buffer, including unsaved text. The graph's original pin remains separately labelled.
[Find](workspace-viewer.md) searches working text, including unsaved edits.

## Limits

The registry requires one durable operation journal. External promotions cannot
be automatically merged into a divergent candidate. The service never removes
filesystem locks automatically. See the [operation ownership and recovery contract](../../../src/laomedo/skills/operations/README.md#registry-and-journal-ownership).
Binary bytes cannot be edited in place; directory uploads, Git publication and
crash-persistent browser buffers are unsupported. Remote private repository
authentication is a separate integration concern.
