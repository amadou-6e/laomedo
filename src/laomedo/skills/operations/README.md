# Skill operation records

`SkillProposal` and `FileEdit` admit model-supplied content; `EditorProvenance`
admits host-supplied attribution. `SkillCommit` groups a new journal entry and
`SkillOperationResult` groups its public result. `SkillComparison` and
`SkillFileChange` describe a historical-to-current comparison. Each has an
explicit `to_record()` or `to_payload()` projection at its existing journal or
public boundary. `from_payload()` preserves existing manual admission errors.

`SkillCommit.to_record()` preserves the exact hash preimage: import commits omit
draft/policy keys; edit commits include them; optional editor fields stay omitted
unless supplied. Timestamps and nonce strings keep their existing formats.
`ImportedSkillEditor` describes a registry import, never a human/agent edit.

`SkillOperations` owns SQLite transactions, replay, authority, commit hashes and
filesystem effects. Existing journal readers remain unchanged. Comparisons carry
the retained base commit as an extensible JSON boundary value rather than
rejecting historical fields with a new write schema. Changed files themselves
are typed. A comparison never changes canonical latest or performs Git publishing.
