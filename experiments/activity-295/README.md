# Activity presentation acceptance

Initial production changes: Laomedo issue295 / PR298, base fc0cfa3ad, tested
head8bd1279db. Specification: specs PR433, head06db633. Additional concurrent
activity refinements later landed on fix/295; those are outside this evidence.
Independent review is pending; the reviewer returned only a quota refusal.

The production build passed. GraphAgents38 tests and the separate current
per-node activity3 tests passed. A local setup initially placed the latter suite
in the wrong folder; correcting placement resolved that import failure. Combined
with the assistant suites,73 tests passed at activity8bd1279/sidebar4ea6234eb.

`ActivityPreview.tsx` renders the real GraphAgents component against an existing
real retained Codex run. `build.mjs` builds a focused read-only entrypoint using
the existing pinned upstream frontend configuration. `preview.py` serves it on
loopback and forwards GET requests to the existing app, preserving ordinary
authentication/origin checks. It rejects mutations and does not export or log
credentials, copy sessions or disable authentication. Opening sends no inference.

CoBrowse verified the retained answer, expanded search, real filtering from two
messages to one, close clearing back to two, both search controls, and centered
empty telemetry. Screenshots stay ignored. The optional fake ghost cards were
not selected. The original full-app proxy prototype had auto-login/bootstrap
errors and is not claimed as full-app acceptance; the focused entrypoint avoids
that unrelated bootstrap entirely. Fresh headless contexts without a login are
not evidence of a successful authenticated check (`check.mjs` is an earlier
unsuccessful full-app probe). No fixture is represented as real retained data.
