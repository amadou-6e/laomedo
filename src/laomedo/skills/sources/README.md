# Skill source discovery

Sources discovers admitted local or public HTTPS repository sources, retains
choices and imports exact immutable Skill bytes. Reading does not execute Skill
content, advance an established canonical latest pointer or grant editing authority.

## Ownership and object nomenclature

| Concern | Defining module | Object or function vocabulary |
| --- | --- | --- |
| Choice coordination, index and registry import | service.py | SkillSources: discover, revisions, resolve |
| Repository cache, refs, entries and blobs | repository.py | GitSkillSource: repository, entries, read_blob |
| Local root admission and reading | local.py | LocalSkillSource: admit, discover, read |
| Bundle byte and path admission | bundle.py | validate_bundle, validate_bundle_path |
| Names and exclusions | utils.py | skill_name, excluded_parts |
| Admitted structured values | models.py | AdmittedSkillSource, SkillSourceChoice, SkillRepositoryRef, SkillRepositoryEntry, SkillRepositoryState, PendingSkillImport |
| Source policy | settings.py | Fixed exclusions and entry limits |
| App transport | ../interface/sources/ | Client, server, request handler, Settings and explicit CLI startup |

Source identifies an admitted read capability. Choice identifies a selectable
Skill folder. Ref binds a named revision to a Git commit; Entry records Git mode,
kind and object identity; State groups the cache directory and captured refs.
Import groups candidate bytes and provenance before validation. Their Pydantic
models keep exact wire projections; dynamic persisted index keys remain maps.

## Method vocabulary

`SkillSources.discover(source)` merges admitted choices and atomically replaces
the index. `revisions(source, choice)` validates bounded candidate bundles before
registry writes. `resolve(source, choice, revision)` verifies a previously offered
immutable reference. `_source`, `_register` and `_save` own admission, publication
and index replacement respectively.

`GitSkillSource.repository(source, refresh=False, *, deadline)` captures an owned
bare repository and its refs. `entries(repository, commit, deadline)` admits tree
metadata; `read_blob(repository, entry, deadline)` checks mode and size before
reading. `_run` owns the source read process; `_cache_bytes` counts one observed
stat sample per regular file, ignoring vanished entries but propagating other
inspection failures.

`LocalSkillSource.admit` validates allowed roots and link/reparse boundaries;
`discover(root, deadline)` finds bounded Skill folders; `read(folder, deadline)`
returns admitted bytes or the missing-SKILL.md result. Model constructors and
`to_record` projections keep display labels and wire shapes explicit.

## Execution policy and constraints

HTTPS Git reads exclude host credentials and interactive prompts, disable global
Git configuration and hooks, refuse redirects and allow only HTTPS. The trusted
constructor-only repository_provider capability enables isolated file reads for
internal tests; HTTP cannot enable it. Source content is never executed.

The source-owned process loop spools output, checks its output/cache bounds every
50 ms and uses a 45-second command limit within one 60-second operation deadline.
The cache bound remains 128 MiB. Ref, entry, file, bundle, depth and option caps
remain enforced before publication. This loop is the explicit source-policy
exception to the general GitCommandRunner; this module does not claim a single
shared native execution path.

Termination retains the existing process-group policy and final process wait.
That final wait is not bounded and process-tree cleanup is not independently
confirmed. Shared-runner adoption, verified Windows containment and a new public
cleanup-uncertainty outcome require separate hardening and acceptance; none is
implied by this structural boundary. Existing public errors and discovery fallback
remain unchanged. Internal controls do not establish real browser acceptance.
