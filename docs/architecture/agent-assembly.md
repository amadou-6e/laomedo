# Existing Agent source assembly

Issue #205 / PR #250 assembles existing work rather than implementing a second
Agent architecture. Source: `refactor/237` at
`8f7b184573cc0d6655d3b61a59f550d84e67253e`, including earlier ownership,
provider-neutral lifecycle, typed Agent records and Agent workspace corrections
from the original branches. Representative checkpoints: `eb1f5e8c`, `75ce39d3`,
`b36f20ed`, `4ff59d59`, `fa33f94d`, `b614cf34`.

The independently based integration starts at develop `20df788f`; it does not
merge the mixed source branch wholesale. Selected Agent source, caller migration,
host runner HTTP, exact-daemon lease dependencies, graph run records and package
resources are assembled together. GitHub/Skills domain implementations remain
those of develop. Later Skill polishing and independent GitHub PR #249 remain
separate. The earlier small import-only checkpoint is superseded by this source.

The source has active ACP behavior. Existing draft specs #403 and PR #214 are
not represented as accepted requirements or freshly verified runtime evidence.
The exact pinned py-docker `49652f4` and ACP SDK `0.12.1` are required; an older
shared test environment initially failed two controller controls because it lacked
`Mount`. Task-owned dependency paths preserve the intended API and other services.

## Current checks and remaining work

Provider and runner HTTP imports succeed. The installed-wheel Agent suite passed
452 cases in 134.119 seconds with four skips, outside checkout. The package import
origin was explicitly checked before running; an earlier target had Windows ACLs
that caused Python to fall back to an older installed package and is not acceptance.
The wheel SHA256 is
`1a5bd3ab0cc5e7df0f17e37cf8b8f9cbf03987ff382ca8dae04881facdc9f844`.
Seven required provider/resource/API entries were verified, with no retired
runtime/provider/Activity package entries. A focused 33-case source run passed
error-catalogue and credential-byte compatibility checks after integration fixes.
No real provider turn or browser acceptance is inferred.

All 162 selected Python implementation files match the existing source branch's
AST exactly; integration changes are caller, packaging, test-ownership and
catalogue corrections. The earlier 122 tests belong to the superseded import-only
checkpoint and do not establish this larger assembly.

441 original example/campaign files are preserved and committed-byte verified on
`exp` at `8b8734ced8cadf8542f680b64df31561c855ed6d`, under
`archives/agents-205`. The manifest maps original paths, byte counts and SHA256.
Archived `.gitattributes` has a non-active `.source` name so it cannot normalize
sibling data. Initial line-ending normalization was detected and corrected before
any production removal. Examples/campaigns still remain in production until their
callers and useful regressions are migrated; this is not a completed removal claim.

Whole `src` Python/mjs physical lines: 32,288 on develop versus 36,747 after this
assembly (+4,459). This includes pre-existing ACP and typed-record work absent
from develop, not a claim of source reduction from relocation. The source origin
and further consolidation must be considered before claiming the requested parity.

Full core discovery exposed historical campaign imports through retired Agent
paths. These remain an integration blocker; they are not hidden by compatibility
shims or discarded to obtain a passing count. Maintained Skill caller imports were
corrected without copying unmerged Skills or GitHub domain implementations.
No paid model request, credential transfer or remote resource mutation occurred.

Required before acceptance: finish caller/resource/CLI/template integration,
compare core discovery and installed wheel behavior, address regressions and
public error coverage, consolidate examples, preserve selected campaigns on exp
before production removal, update their regression/CI dependencies, and complete
full substantive reviewer validation. Unknown live saved embedded source remains
a compatibility gap. Actual changed provider/user stories and requesting-owner
validation remain required before merging. No fixture result is a deliverable.
