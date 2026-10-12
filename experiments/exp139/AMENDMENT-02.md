# Prospective frozen-context transport correction

2026-10-11, before activation, model turns or acceptance writes. A network-disabled
run of the actual prepared graph found that Langflow's text input processing
changed JSON escape sequences in the real issue body. The earlier short fixture
did not expose this. No request reached a live runner.

Encode the frozen context and bounded task as base64 UTF-8 in the exported issue
node, decode them strictly inside the node, and retain the canonical context
digest check. This is transport encoding, not encryption. A regression now checks
exact task/context round-trip through the imported graph with newlines, quotes,
tabs, backslashes and non-ASCII text. Rebuild only the three graph exports from
the existing frozen input; do not re-fetch the issue or baseline. Refresh the
prospective manifest and obtain review before activation. Configuration, budgets,
report bytes, provider custody and permissions are unchanged.

Accepted bounded limits from the first pre-run review: the original 600 seconds
include agent execution and verification; a slow turn can safely expire before
publication. This experiment does not expose or exercise resume, although the
underlying authenticated endpoint remains available. Resumed publication is
refused and the shared four-turn and one-write-attempt budgets still apply.
Before activation, independently check the source checkout is clean at the
recorded baseline. Keep both new processes alive through final readback.
