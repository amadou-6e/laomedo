# Registry records

`SkillStore` owns immutable bundles, draft filesystem effects and explicit
promotion. `models.py` owns new record construction: `SkillRevision`, `SkillDraft`,
`FrozenSkillDraft`, `SkillRevisionReference`, `SkillTreeReference`,
`SkillPolicyReference` and `SkillValidationResult`.

`FrozenSkillDraft.from_review()` groups the admitted draft identity, observed
files, validation results and editor provenance. It derives the comparison and
eligibility together, without filesystem writes or promotion. `to_record()`
serializes the existing JSON keys, including explicit nulls and empty lists.
Revision and draft constructors carry fields together until `to_record()` reaches
the existing file writer. A policy reference identifies the admitted policy; it
does not authorize an edit.

These strict models construct new writes. Existing revision/result readers keep
their integrity checks and tolerate their existing historical shapes; they do
not validate historical files against these write models. Content hashes, patch
bytes, latest pointers and separate compare-and-swap promotion are unchanged.
