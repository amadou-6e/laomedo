# Shared and Skills merge-readiness audit

Audit date: 2026-10-31. Implementation source: `0a26c60fdcb703cf81ab77a7fad21d2f74749f18`.
Develop baseline: `5ffab075bbab50e195a3c8a375a83dff55a70fea`.
Tracking: [issue #237](https://github.com/amadou-6e/laomedo/issues/237).

This audit covers Shared preparation and Skills. GitHub and Agents as complete
modules are outside its verdict. Neither audited slice is independently ready
to merge into develop. No merge or owner acceptance is recorded here.

## Architecture and cleanup

The defining references are [Git](../../src/laomedo/git/README.md),
[HTTP](../../src/laomedo/http/README.md) and
[Skills](../../src/laomedo/skills/README.md). They describe concern ownership,
object/method vocabulary and contracts. Verification chronology belongs here.

The cleanup removes eleven old-source/body/hash-chain proof JSON files and two
capture scripts. Current behavior, migration-target, error-catalogue and archive
integrity checks remain. Persisted/wire golden cases remain contracts; archived
executions retain their original bytes and revision attribution.

Five maintained graph templates contained stale embedded components. Their source
and recognized source hashes now follow canonical component files. All other
graph values are preserved, including selections, inputs, outputs, edges, handles
and positions. A single current masked-graph contract protects those values.

Refreshing stale embedded code changes what those templates execute: PR feedback,
Claude Skill feedback, description instructions and cleanup-error propagation now
follow the canonical components. The seven refreshed nodes in five example files
have not been newly run against real services by this audit. Their import/structure
checks and the retained component's earlier real execution are supporting evidence,
not acceptance of each refreshed template. PR example changes belong to the later
GitHub slice when partitioning the audit patch.

The broad `skill_feedback_task_only` check is replaced by the common
`skill_input_vertices` admission in `integrations/langflow/feedback/pr.py`.
`feedback_edge` calls it before operation preparation. It requires exactly one
controller Task and admits at most sixteen independent read-only Skill references;
other inputs and mutating dependencies refuse before dispatch. The dedicated
Langflow rejection control passes, but does not establish real failure-path UI.

The private REST redirect alias is removed. Its internal archived-probe consumer
uses explicit hash-checked import adaptation. Archived sources remain unchanged.
Four local retired directories containing only bytecode were removed, including
`skills/ingestion` and `skills/workspace`; no implementation source was deleted
by cache cleanup.

## Observed checks

| Check | Result and scope |
| --- | --- |
| Project-wide Black | Pass: 781 files unchanged at the source above |
| Full Windows internal suite | 1,322 tests in 629.391s; one removed-package assertion failed because of a cache-only retired directory; 18 skipped |
| Affected checks after cache cleanup | Pass: 84 tests in 53.303s, including the exact failed assertion, migration, HTTP, catalogue, architecture and native Windows process controls |
| Separate Langflow controls | All 22 test modules pass in isolated processes; aggregate discovery's root/graph module-name collision is a harness constraint |
| GitHub CI at the source above | [Work Graph](https://github.com/amadou-6e/laomedo/actions/runs/41197088273) and [Black](https://github.com/amadou-6e/laomedo/actions/runs/41197088246) pass; package tests cover Python 3.10/3.13 |
| Wheel build | Pass; local artifact SHA-256 `761a076f408a0848af6de82145625d6e773ecadf25d8068026db481c609484df` |
| Isolated wheel smoke | Six defining imports, packaged authoring instructions and an actual Git version command pass outside the source checkout; no foreign feature/framework loads |
| Real local source | Actual refactoring skill discovered, pinned and inspected; owned scratch removed and original bytes unchanged |
| Real HTTPS sources | Public `anthropics/skills` clones; full discovery reaches the 60-second operation budget and returns `repository_limit_exceeded`. Credential-free `amadou-6e/my-skills` returns `repository_access_unavailable`; its cause is not established |
| Real viewer | Five fresh read-only stories pass: genuine edited revision/history, both edited files, and each file's parent-to-current comparison. Zero graph runs, model requests or Skill/graph writes; all eleven observed Node/Edge processes exited |

The viewer uses the retained `ca3f1e9` build, not a newly installed cleanup build.
All sixty Shared/Skills Python and packaged authoring files match current Git
source after universal-newline source decoding; Python ASTs match. Wheel and
installed bytes match exactly. One working source file differs in LF/CRLF
representation. This is source equivalence, never registry-byte normalization.
Viewer/frontend/Skill component Git sources are unchanged. The earlier real
Agent edit is historical; this audit freshly viewed its real retained result.

The first viewer attempt captured the states but its response-body observer did
not settle. Only its exact owned Node/Edge lineage was stopped. A corrected
private harness used bounded HTTP asset reads; that second attempt passed and
confirmed registry/history/native records and existing graphs remained unchanged.
This recovered harness failure is not product acceptance.

## Independent merge boundary

An exact directory-only Git/HTTP/Skills patch applies cleanly to develop in a
detached checkout. Imports of Git, HTTP, registry, sources, operations and
inspection pass. Existing Agent import fails on removed
`laomedo.skills.registry.utils`; Issue and PR clients fail on removed
`laomedo.skills.sources.transport`. The viewer imports successfully.

This diagnostic intentionally measures caller closure, not a complete proposed
slice. Shared must migrate the existing HTTP/Git callers in the same PR. Skills
must migrate its existing Agent callers in the same PR. Old implementations must
not be kept alongside replacements. The eventual slices need independent tests
against their actual develop bases; integrated-candidate CI does not prove them.

## Acceptance still required

- A caller-complete, independently tested develop-based Shared preparation slice.
- A caller-complete Skills slice with its relevant specification/review coverage.
- Real user-story validation of the refreshed example graphs appropriate to each
  owning module; their canonical source/hash alignment alone is insufficient.
- A verified real cleanup-uncertainty discovery UI path. Internal process controls,
  ordinary outages and synthetic error codes do not establish that story.
- Resolution or explicit supported-input assessment of the observed public-source
  discovery budget refusal; no budget or credential boundary was widened here.
- Requesting-user inspection and validation of the final applicable graph stories.

Independent cleanup review and green checks do not replace these requirements.
Other existing Agent/provider, durable job/trace and code-length constraints are
not waived by this audit.
