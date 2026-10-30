# Agent workspace skill delivery

This leaf owns run-local Git exclusion evidence and verification of already
materialized immutable skills. It does not own registry editing, remote source
selection, GitHub workflows or native provider skill execution.

## Ownership and nomenclature

| Concern | Defining owner | Vocabulary |
| --- | --- | --- |
| Git metadata and skill-byte checks | `utils.py` | `_exclude`, `install`, `verify`; focused function-only module |
| Refused preparation/verification | `errors.py` | `WorkspaceSkillError`; existing ValueError identity domain, safe code and argument shape |
| Prepared skill evidence | [canonical Agent models](../../agents/base/models.py) | `AgentSkillBinding`; skill/revision/tree/file identities and offered discovery evidence |
| Git exclusion evidence | [canonical Agent models](../../agents/base/models.py) | `SkillGitExclusion`; enabled state, optional rules and exact exclusion-byte digest |

Binding names the installed identity/evidence pair. Exclusion names observed
run-local Git metadata, not registry policy or authorization. The two existing
Pydantic models remain defined once in Agent base models during this pure
relocation. No duplicate model, forwarding models.py or new provider-specific
record is introduced. Their existing construction and model_dump projections,
including omitted disabled keys, remain unchanged.

## Function interfaces

| Function | Responsibility and effects |
| --- | --- |
| `_exclude(workspace)` | Return the admitted .git/info/exclude path, or None without Git metadata; refuse redirected, linked, special or hard-linked metadata. |
| `install(workspace, skills)` | Append the existing per-skill exclusion rules and return enabled/rules/exclude_sha256 evidence, or enabled=False without Git. It installs exclusion rules; BaseAgent materializes the files separately. |
| `verify(workspace, skills, exclusion)` | Check exact installed names, pinned byte hashes and unchanged exclusion evidence before dispatch/publication. It does not claim the provider used an offered skill. |

The functions retain dictionary/list boundary signatures and payloads in this
checkpoint. BaseAgent forms the existing canonical preparation records. Inventory,
hashing and link detection import the defining general Skills registry helpers;
general Skills never imports this Agent-only package. No Git subprocess belongs
in this leaf: independent baseline creation is in ../baseline.py and reusable
mechanics remain in laomedo/git.

## Migration and failures

The original helper bodies, byte handling, side-effect order and stable codes
are preserved. All three resulting producer owners (baseline, cleanup and this
leaf) need catalogue guards; moving the path must not drop those checks.
WorkspaceSkillError translation to RunnerError remains with existing callers.

The offline symbol map migrates known functions directly. Historical provider
module-valued workspace_skills exports require explicit defining imports rather
than a fake combined namespace. Preserved exp104 probe/worker sources retain
their exact bytes; direct legacy execution requires migration. Internal import
migration controls are not live Agent or graph acceptance.

Maintained tests load the preserved EXP104 worker/probe through
`tests/retained_native_probe_loader.py`: verify original hashes, migrate only
imports/qualified symbol reads, compare all other AST structure and keep the
original `__file__` for resource resolution. A temporary test-only worker name
is removed immediately after import. No canonical runtime alias is installed;
neither probe's main entrypoint is invoked. Frozen source/blob contracts work
with shallow CI and compare installed helper bytes to the checkout source.
