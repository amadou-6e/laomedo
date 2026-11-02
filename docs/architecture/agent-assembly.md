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

Provider and runner HTTP imports succeed. A full concern-owned Agent regression
run is in progress; the earlier 122 tests belong to the superseded import-only
checkpoint. They do not verify this larger assembly. No paid model request,
credential transfer or remote GitHub mutation was performed.

Required before acceptance: finish caller/resource/CLI/template integration,
compare core discovery and installed wheel behavior, address regressions and
public error coverage, consolidate examples, preserve selected campaigns on exp
before production removal, update their regression/CI dependencies, and complete
full substantive reviewer validation. Unknown live saved embedded source remains
a compatibility gap. Actual changed provider/user stories and requesting-owner
validation remain required before merging. No fixture result is a deliverable.
