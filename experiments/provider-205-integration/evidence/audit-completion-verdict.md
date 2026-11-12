# Cleanup recheck: base 4bf245a7 → head 42954ed4

**Bottom line:** F-01, F-02 and F-03 are fixed, the corrections introduce no new defects, and the previously unread test hunks are now covered. The cleanup verdict is APPROVE for code and docs. There is one optional edge case and no further recheck is needed.

## Corrections

**F-01: resolved.** The seven orphaned OpenCode Console entries are gone from the error catalogue, and the JSON separator was fixed. No producer in `src/` remains.

**F-02: resolved.** The retired `runner_trace_bridge.py` producer name is gone from `test_catalogue.py`.

**F-03: resolved.** The `routes.py` detail endpoint now reads one page of 200 rows and projects it.
- **Why one page is enough:** `ActivityStore.append` (`store.py:115-156`) keeps a single snapshot row per invocation and updates it in place, at the sequence where it was first written. `capture.py:119-141` writes that snapshot before the page's records. So the latest snapshot is in the first page.
- **Incomplete runs are still suppressed:** for `invocation_boundary_unverified` and `activity_projection_limit`, the original reason texts are kept and usage and cost are cleared.
- **The new regression test** (`test_incomplete_current_snapshot_never_claims_known_usage_or_cost`) uses a real current snapshot through the store and HTTP route, and checks both reasons.
- **Optional edge case:** if a provider page hits `activity_projection_limit` before any snapshot was saved (`normalizer.py:186-195` leaves `projection=None`), capture stores records without a snapshot, and `project()` raises a `ValueError`, which surfaces as HTTP 500. This behaviour already existed before the cleanup and is not a regression. If you want, map it to a stable code later.

**`test_boundaries` import:** `CLI_VERSION` now comes from its defining module, `claude/settings.py`.

**Provider-import guard:** it now matches the bare package names and catches `from laomedo.agents.agents import codex`. This closes the false-negative limit noted in the last review.

## Previously unread tests (`audit-unread-tests.diff`, read in full)

- **Projector fixture:** `audit-fixture-conservation.json` confirms all seven retained cases have unchanged events, kwargs, keys and expected JSON. Only the projector label changed, from `shared` to the actual provider. The removed `shared-opencode-dispatch` case was the duplicate that relied on the old automatic provider dispatch. I read the diff hunks, but did not re-verify the hashes myself.
- **Claude, Codex, OpenCode and graph-Activity tests:** they now import each provider's own `project` and add `.to_payload()`. Every assertion is otherwise unchanged.
- **Timeout-reconciliation bridge tests:** two were removed, and they exercised only `RunnerTraceBridge.observe_terminal`. The current invariants are still covered elsewhere:
  - the `HttpAgentBridge.status` privacy allowlist: `test_native_timeout_reconciliation.py:176-178`;
  - `attempt_finished` pass-through: `test_langflow_join_http.py:166-173` and the codex component tests;
  - the finished-attempt and restart handling of unknown receipts: retained at `:188+`.
- **`test_opencode/test_auth.py` deletion:** it only exercised the retired Console loader, redirect handler and route rejections. `opencode_organization_context_mismatch` remains in the current error codes.

**Deleted source bodies** (`trace_bridge.py` and the OpenCode `auth/*` files) are accounted for by your retirement authorization plus a check that no current code references them (grep across `src`, `frontend`, `tests` and `docs`). I did not review them line by line.

## Coverage

- **Read in full this round:** `audit-corrections.diff`, `audit-unread-tests.diff` and `audit-fixture-conservation.json`.
- **Source traced:** `store.append`, `capture` append order, the `normalizer` limit path, the `ActivityPage` validator, and `HttpAgentBridge.status`.
- **From the previous round:** the rest of `audit-source.diff` and `audit-tests.diff` remain covered by that read.
- **Not verified:** the full-suite run, which you said is still in progress, and hosted CI.

## Verdicts (base 4bf245a7 → head 42954ed4)

- **Cleanup code and docs:** APPROVE. No concrete findings remain; the projection-limit edge case above is optional.
- **Visual:** not applicable. The only change is removing error-catalogue entries that can no longer be produced, and no reachable UI behaviour changes.
- **Acceptance:** this cleanup has no live acceptance. The earlier Codex graph acceptance applies only to its own revision; the graph review follows next, as the human asked.
- **Not authorized:** merge or issue closure.