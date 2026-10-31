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
| Candidate edits | `models.py` | `FileEdit`, `SkillProposal`; admit paths/content and project the existing proposal payload |
| Execution provenance | `models.py` | `EditorProvenance`, `ImportedSkillEditor`; evidence supplied by the trusted boundary, not model-granted authority |
| History and receipts | `models.py` | `SkillCommit`, `SkillCommitReceipt`, `SkillOperationResult`; preserve record and response shapes |
| Historical comparison | `models.py` | `SkillFileChange`, `SkillComparison`; changed file metadata and exact patch presentation data |
| Public dictionary admission | `utils.py` | proposal(value); use the canonical SkillProposal directly |

## Service interfaces

| Method | Responsibility and effects |
| --- | --- |
| `connect()` | Open the local journal with the existing SQLite connection policy. |
| `prepare(skill_id, revision_id, commit_id='')` | Check editing policy and selected base, seed initial imported history when needed, and reserve a short-lived request ticket. |
| `apply(ticket, operation, editor=None)` | Validate authority/base/policy, stage the entire file batch and atomically record the resulting immutable revision/history or reject the batch. Preserve replay and conflict behavior. |
| `history(skill_id, revision_id, before='')` | Verify the selected bytes and return a bounded parent-chain page without patch bodies. |
| `diff(skill_id, commit_id)` | Recompute/verify a commit's patch against its parent and return the stored record; no mutation. |
| `compare(skill_id, commit_id, revision_id)` | Compare historical snapshot bytes to the viewer's pinned current revision, retaining additions/deletions, binary metadata and missing-final-newline evidence. |

## Canonical record interfaces

SkillProposal.from_payload/to_payload and EditorProvenance.from_payload/to_payload
own existing dictionary boundaries and validation. FileEdit validates path/content;
SkillProposal validates unique paths; EditorProvenance validates provenance.
SkillCommit.to_record, SkillCommitReceipt.to_payload, SkillOperationResult.to_payload
and SkillComparison.to_payload retain outward shapes. SkillOperationResult's
serialize_commit/serialize_skill hooks preserve its established nested projections.
ImportedSkillEditor and SkillFileChange need no behavior beyond canonical Pydantic
construction. No duplicate proposal validator or commit identity model is added.

General registry path/hash/policy/diff functions remain in their defining registry
modules. HTTP auth/routes/limits belong to skills/interface/operations, and host
publication belongs outside this feature. Error translation/catalogue coverage and
real edit/history/diff browser acceptance remain required; internal fixtures are
not a user-facing demonstration or acceptance result.
