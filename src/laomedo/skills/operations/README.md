# Atomic skill operations

SkillOperations owns the authorized multi-file editing transaction and its
commit-style SQLite journal. Byte revisions remain immutable registry objects;
history commits can differ even when their resulting bytes match. The journal
is trusted local state, not a signed or tamper-proof audit log. Applying edits
does not promote canonical latest or publish Git commits.

## Concerns and nomenclature

| Concern | Defining owner | Vocabulary |
| --- | --- | --- |
| Authorization, replay, staging and journal effects | `service.py` | `SkillOperations`; one atomic owner, not separate Store/Ledger facades |
| Candidate edits | `models/` | `FileEdit`, `SkillProposal`; admit paths/content and project the proposal payload |
| Execution provenance | `models/` | `EditorProvenance`, `ImportedSkillEditor`; evidence supplied by the trusted boundary, not model-granted authority |
| History and receipts | `models/` | `SkillCommit`, `SkillCommitReceipt`, `SkillOperationResult`; preserve record and response shapes |
| Historical comparison | `models/` | `SkillFileChange`, `SkillComparison`; changed file metadata and exact patch presentation data |
| Public dictionary admission | `utils/proposal.py` | proposal(value); use the canonical SkillProposal directly |

## Service interfaces

| Method | Responsibility and effects |
| --- | --- |
| `connect()` | Open the local journal with its SQLite connection policy. |
| `prepare(skill_id, revision_id, commit_id='')` | Check editing policy and selected base, seed initial imported history when needed, and reserve a short-lived request ticket. |
| `apply(ticket, operation, editor=None)` | Validate authority/base/policy, stage the entire file batch and atomically record the resulting immutable revision/history or reject the batch. Preserve replay and conflict behavior. |
| `history(skill_id, revision_id, before='')` | Verify selected bytes, materialize the retained imported root when needed and return a bounded parent-chain page without patch bodies. No edit policy or ticket is required. |
| `diff(skill_id, commit_id)` | Recompute/verify a commit's patch against its parent and return the stored record; no mutation. |
| `compare(skill_id, commit_id, revision_id)` | Compare historical snapshot bytes to the viewer's pinned current revision, retaining additions/deletions, binary metadata and missing-final-newline evidence. |

## Canonical record interfaces

SkillProposal.from_payload/to_payload and EditorProvenance.from_payload/to_payload
own dictionary boundaries and validation. FileEdit validates path/content and mutually exclusive byte representations;
SkillProposal validates unique paths; EditorProvenance validates provenance.
SkillCommit.from_import/from_registered_revision construct retained import or
legacy revision registrations; SkillCommit.to_record preserves their hash payload.
SkillCommitReceipt.to_payload, SkillOperationResult.to_payload
and SkillComparison.to_payload retain outward shapes. SkillOperationResult's
serialize_commit/serialize_skill hooks preserve its established nested projections.
ImportedSkillEditor and SkillFileChange need no behavior beyond canonical Pydantic
construction. Proposal validation and commit identity each have one canonical owner.

`SkillCommit.from_import` projects the registry's durable `SkillImportRecord`
into an initial commit with no parent and all imported paths/differences against
an empty tree. The same event yields the same identity on refresh and restart.
An immediate SQLite transaction prevents concurrent first reads from duplicating
the root; subsequent history reads do not acquire an edit lock. The first edit
parents that commit. When canonical revisions were promoted outside an older
journal, their verified ancestry is registered after the root, with original edit
times and provenance explicitly unknown. The latest registration becomes the head;
editing that revision requires its exact Base Commit, as for any non-root edit.
Existing journal heads and legacy
empty-root patches retain their original identities and verification behavior;
no historical commit is rewritten. Legacy imports without a journal are labelled
with unknown original import time, rather than assigned an invented import date.

General registry path/hash/policy/diff functions remain in their defining registry
modules. HTTP auth/routes/limits belong to skills/interface/operations, and host
Git/source publication belongs outside this feature. Error translation/catalogue coverage and
real edit/history/diff browser acceptance remain required; internal fixtures are
not a user-facing demonstration or acceptance result.

## Manual editor and registry publication

`ManualSkillEditor` in `manual.py` is the trusted local viewer's write boundary.
Its canonical request/state/receipt and host grant models live in `models/`.
The closed public failure vocabulary lives in `settings.py`; presentation belongs
to the shared catalogue. Existing Agent/ordinary operations never promote latest.

| Method | Interface and effect |
| --- | --- |
| `editor(skill_id, revision_id)` | Read pinned selection, journal head, canonical current and effective manual grants; never expose tickets or policy contents. |
| `save(**ManualSkillSave)` | Persist a UUID-bound exact proposal and backend-only ticket before using `SkillOperations.apply`; read an existing result after a lost reply, without bypassing ordinary apply expiry. |
| `publish(**ManualSkillPublication)` | Require separate publication permission, freeze the cumulative canonical-to-candidate diff under the current policy and CAS canonical latest. Persist the frozen draft before promotion and a confirmation receipt afterward. |

`ManualSkillPermissions` defaults both edit and publish to false. Grants only
apply to Skills with configured versioned edit policies. The browser cannot
change either. A manual save records trusted operator/backend provenance; it
does not claim a separately verified human or Agent. Publication retains the
candidate's existing history and a separate durable promotion receipt. Replaying
an identical UUID cannot add a commit; reusing it with different content conflicts.
The registry's retained promotion log reconciles a lost publication reply even
after a later edit. `confirmed_at` is the receipt confirmation time, not an
invented original publication time after crash recovery.

Neither action edits source repositories or existing graph pins. No model runs,
validation commands or Git operations execute through this interface. Editing
binary contents in place and crash-persistent browser working copies remain unsupported.
Binary uploads/moves/deletions use the same atomic transaction under asset policy.

Confirmed save/publication receipts remain readable for the same exact request
after write-grant revocation or policy changes. This is reconciliation of an
existing effect, never renewed mutation authority. Uncompleted requests still
require the current manual grant and exact applicable policy.


## File edit representations

| FileEdit method | Contract |
| --- | --- |
| `from_payload(value)` | Admit exact text/deletion, canonical base64 or immutable source-copy shapes; reject coercion/mixed forms with stable categories. |
| `to_payload()` | Keep old text/deletion wire dictionaries unchanged, including replay equality; emit encoding/source_path only for their new forms. |
| `to_bytes(base)` | Return exact replacement bytes or deletion; copy only from the reserved before-inventory, independent of deletion order. Never read a host path or same-batch new file. |

Binary content is not a separate publishing path. Raw bytes determine tree/file
identity; the journal retains old/new binary metadata and hashes. Save and
cumulative promotion both require exact allowed paths, additions/deletions and
size policy. Non-text changes additionally require allow_assets and a fixed inert
suffix from registry settings; script/dependency restrictions remain intact.

Changed NUL-containing files use the same binary admission as non-UTF-8 bytes;
text-path policies refuse them unless they are explicitly permitted inert assets.
Valid UTF-8 without NUL remains text regardless of filename suffix.

## Registry and journal ownership

A writable registry is paired with one durable operation journal. Keep both in
backups. Commit identifiers belong to that retained journal; rebuilding it from
bundle bytes records new events and does not restore lost commit references.
The import root remains stable through its retained import record.

Publication requires the registry's current revision to be an ancestor of the
candidate in this journal. A promotion made outside the journal cannot be
silently replaced, even after the viewer refreshes its current revision. The
request returns `skill_manual_stale`, preserves the candidate and newer registry
bytes, and requires maintainer-led reconciliation. Automatic merging, branching
and reconstruction of another journal's edit provenance are unsupported.

For graph operations after initial history has been backfilled, use the current
history head as Base Commit in the Skill node's Advanced settings. An empty Base
Commit admits only the initial import, preventing an accidental edit of a newer
head. The hidden Edit Request reader supports previously saved feedback graphs;
new nodes expose no such field and receive edits through Operation or the manual
editor. This is saved-graph compatibility, not a new authoring control.

Registry `import.lock` and `promotion.lock` exclude simultaneous filesystem writes.
They have no automatic expiry: a reader cannot distinguish a crashed writer from
a slow active writer. A blocked promotion is reported as an unconfirmed service
result, not a changed base. Check result retains the same publication identity.
If a lock persists after a crash, a maintainer must stop all writers to that
registry, verify that no write is active, back up registry and journal, and only
then remove the abandoned lock before restarting the service and checking the
same request. The UI does not delete locks or offer automatic lock repair.

### Pending writes and divergent-history maintenance

The viewer retains an unconfirmed request in memory and refuses Close/Discard
while it is pending. Check result reconciles that identity. Reloading the page
loses the browser's pending state; it does not cancel or reverse the durable
service request. A persistent lock therefore blocks closing through the viewer
until the write can be reconciled. This is a current usability constraint, not
an implemented cancel or automatic lock-recovery feature.

There is no self-service journal reconciliation command. Maintenance requires
explicit owner review of both the newer canonical files and retained candidate,
a backup of registry and journal, and stopping competing writers. Use the
[registry draft and reviewed-promotion API](../../../../docs/features/skills/registry.md)
to prepare the chosen merged tree against the exact canonical latest, inspect
its complete diff, freeze it under the existing policy and explicitly promote
that exact draft. This does not waive policy or compare-and-swap checks.

If the reviewed result equals the retained journal head, canonical and journal
are aligned again. Otherwise retain the original journal as a read-only history
archive and configure a new journal for the verified canonical lineage; its
registered entries do not invent the old edit provenance. Preserve old immutable
revision references, and select new Base Commit references explicitly. Do not
delete or rewrite the old journal, or present this maintenance as a UI merge.

## Missing-description guidance

`utils/summary.py` owns `has_description` and `summary_authoring`. It conservatively
preserves existing descriptions and loads packaged Agent instructions only when
a readable SKILL.md has no description. It neither calls a model nor edits files;
the operation service validates and applies authorized proposals. Viewer reads
do not trigger authoring.

Models are organized by proposal, provenance, history and manual concerns under
models/. Independent proposal admission and summary guidance live under utils/.
The fixed error vocabulary lives in settings.py. Service and ManualSkillEditor
retain their operations and persistence responsibilities.
