# Immutable skill registry

The registry owns content-addressed skill bundles, draft working copies, their
review records and explicit promotion. A byte revision is not an operations
journal commit. Source discovery, edit authorization, host publication and Agent
workspace installation remain with their callers.

## Ownership and dependency direction

| Concern | Defining module | Vocabulary |
| --- | --- | --- |
| Filesystem lifecycle | `store.py` | `SkillStore` owns registry roots, immutable revisions, drafts and promotion |
| New record construction | `models.py` | Existing Pydantic references, revision, draft and frozen review records |
| Name and relative-path admission | `paths.py` | `validate_name`, `validate_relative_path` |
| Filesystem reads and record replacement | `files.py` | `is_link`, `inventory`, `read_json`, `write_json` |
| Byte identities | `hashing.py` | `hash_bytes`, `canonical_json`, `tree_hash`, `file_hashes` |
| Editing policy | `policy.py` | `validate_policy`, `validate_draft` |
| Exact review patch | `diff.py` | `patch_for` |
| Failure domain | `errors.py` | `SkillStoreError`, `ConflictError`; stable code, arguments and inheritance |
| Fixed identity syntax | `settings.py` | Existing `NAME` and `HASH` patterns |

Use Store for the object that owns persistence, Reference for an identity binding,
Revision for immutable content metadata, Draft for an open edit and Result for
observed validation. No abstract Base, second ledger or forwarding facade is
needed. Independent helpers are function-only modules; classes and Pydantic
records remain in class-only files. Callers import defining symbols directly.
`files` and `hashing` depend on `paths`; `policy` depends on `paths` and `hashing`;
models derive projections through those helpers; `SkillStore` owns effects.
None of these helpers depends on source services, Agents or an app framework.

## Object and method nomenclature

| Object | Public methods | Meaning |
| --- | --- | --- |
| `SkillStore` | `import_skill` | Copy and verify an initial revision; never replace existing latest |
| `SkillStore` | `revision`, `read_file` | Verify and read immutable metadata or one admitted file |
| `SkillStore` | `create_draft`, `draft_workspace` | Reserve an independent editable copy and locate it |
| `SkillStore` | `freeze_draft` | Observe bytes, policy results, provenance and patch; no promotion |
| `SkillStore` | `promote_draft` | Explicit compare-and-swap promotion under existing locks |
| `SkillReference` | `to_reference_payload` | Project the public skill/revision/tree identity only |
| `SkillRevision`, `SkillDraft` | `to_record` | Preserve existing on-disk keys, order, nulls and empty values |
| `FrozenSkillDraft` | `from_review`, `to_record` | Derive one coherent review result and its existing record projection |
| `SkillPolicyReference`, `SkillRevisionReference`, `SkillTreeReference`, `SkillValidationResult` | No public behavior beyond canonical Pydantic construction | Group admitted identity or observed validation values without introducing a second domain model |

Private store methods retain their existing responsibilities: `_skill`, `_draft`,
`_workspace`, `_revision_dir` locate admitted paths; `_store_revision` copies and
verifies bytes; `_finish_promotion` completes the existing promotion transaction.
Strict models construct new writes. Historical readers keep their existing
integrity checks and tolerate historical shapes; they do not validate old files
against new-write models. A policy reference identifies policy, not authority.

## Compatibility and exact byte behavior

This split preserves function signatures, exceptions and side-effect order.
Private utility spellings become descriptive exported names at their defining
modules: `_hash` becomes `hash_bytes`, `_canonical_json` becomes `canonical_json`,
`_safe_name` becomes `validate_name`, `_safe_relative` becomes
`validate_relative_path`, `_is_link` becomes `is_link`, `_read_json` becomes
`read_json` and `_write_json` becomes `write_json`. The old `utils.py` is removed;
the published symbol migration map is authoritative, with unmapped dynamic/star
access requiring manual migration. No runtime import aliases are installed.

Tree identities retain sorted paths, UTF-8 names and length-prefixed exact file
bytes. Canonical policy JSON retains sorted keys, compact separators, default
ASCII escaping and every admitted extra field. Policy validation stays manual:
no coercion of booleans, integer limits or historical dictionaries is introduced.
Hashing and patch generation preserve LF/CRLF and missing-final-newline differences;
only the existing frontmatter validation view normalizes CRLF. JSON record writes
retain unique pending names, indent/sort behavior, final LF and `os.replace`;
this is atomic replacement without an fsync durability guarantee. Inventory
rejects links/reparse points, hard links, special files and empty directories;
it does not itself enforce byte/count limits. Those limits remain caller-owned.

The EXP-08 probe and tests are retained historical controls, not current runtime
entrypoints or live acceptance. Their original bytes are hash-pinned. CI runs an
explicit temporary import-only migrated copy and preserves their existing test
assertions and standalone probe execution. No observation file is regenerated.
A source hash and non-import AST comparison protect this migration; direct old
probe execution requires an explicitly migrated copy.

D1 is a module split only. Source/Git collaborators, Agent workspace relocation
and shared GitHub domain ownership remain later, separate checkpoints. Internal
controls and reviewer approval do not establish real graph or owner acceptance.
