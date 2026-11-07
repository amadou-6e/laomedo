# PR249 GitHub: tests, specs and migration maps at head `9a741243`

The test consolidation preserves the safety coverage I compared. One specification follow-up is needed: the specs still point at evidence files this PR removes from develop.

## What I compared

- **Issue gateway:** all 17 deleted tests from the old live-issue suite match their new copies in `test_issues/test_gateway.py` line for line, apart from the switch to the shared case factory. That covers:
  - timeout-after-write stays unknown and is never repeated;
  - a concurrent duplicate returns unknown, then confirmed, with no second dispatch;
  - rebinding a reference cannot reuse another run's result;
  - a rejected readback after the write stays unknown;
  - revocation during the read refuses before any write;
  - expired, revoked and foreign grants;
  - incomplete pagination is refused rather than treated as empty.
- **PR feedback:** all 14 deleted tests match `test_pull_requests/test_feedback.py` line for line:
  - ticket identity and replay of the same proposal;
  - a different proposal under the same ticket conflicts;
  - unknown effects are not retried;
  - grant rotation and revocation;
  - wall-clock rollback and monotonic reset;
  - restart replay.

  One test was added: `test_feedback_snapshot_keeps_original_labels_extensions_and_deadlines`, which checks the stored ticket against independently written expected values and boundary times.
- **No borrowed setup:** the old suite reused another class's setup (`setUp = LiveGitHubPRTests.setUp`). That is gone; each test now builds a fresh case and owns its temp directory.
- **Shared factories are sound:** `create_case` in `test_issues/utils.py:23-61` and `test_pull_requests/utils.py:26-64` uses the real REST transport, mediation store and gateway. The gateway's grant lookup reads `case.binding` at call time, so reassigning it in the rebinding and rotation tests still takes effect. The case models are mutable, so that reassignment works.
- **Name-level check across the whole test diff:** every deleted test name in the old live-PR, interface, client, HTTP and redaction suites reappears under the new layout:
  - `test_client_uncertain_delivery_and_bad_responses_are_not_rejections`
  - `test_server_unexpected_write_exception_is_unknown_not_rejected`
  - `test_loopback_service_auth_and_error_redaction`
  - the 12 PR gateway tests
- **New independent checks:**
  - `test_intents.py:14-73` recomputes the stored intent hashes from separately written payloads and checks the key sets for modify and close;
  - `test_values.py` checks literal Unicode hash inputs and that invalid values are not echoed in errors;
  - `test_errors.py` checks that every handler and component error code has catalogue text, and that the unknown-write recovery text says "before authorizing another" without "operator".
- **Deleted on purpose:**
  - the agent operation demo's 4 tests, tied to an example now archived on exp;
  - the EXP-44/45 publication probes and the EXP-108 CI test.

  The production no-retry/unknown guarantees they touched are still covered by the gateway timeout and readback tests. The `tests/test_github/README.md` table maps each remaining guarantee to its owning suite.
- **Migration maps:** I traced the changed cli, module and symbol path entries. Every target is a current defining module or symbol, including:
  - `issues.utils.main` → `issues.context.main`;
  - `issues.utils.fetch_context` → `context_reader`;
  - `IssueContextError` → `issues/errors.py`, which exists;
  - `GitHubMediatedTransport` → `transport.mediated`;
  - shared digest, label and URL helpers → `github.contract`.

  The exp19 entry added to `retained-shared-callers.json` pins its bytes and source revision.

## Findings

**G-S-D1 · spec defect · medium · newly exposed**
- Where: `issue-integration/validation.md:41,51,115,153,158,184`.
- The validation page cites unpinned implementation paths that this PR removes from develop (archived on exp at `714db418`):
  - `examples/github-pr/evidence.json`, `four-node-flow.json`, `real-flow.json`, `real-evidence.json` and `operation-feedback-evidence.json`;
  - `original-agent/PROTOCOL.md`, `evidence.json` and `cancellation-evidence.json`.
- Once this merges, those references break. EXP-14/15 links are already pinned to a commit and are fine.
- Needed: a specs errata that points these at the archive revision.

**G-S-Q1 · question · low**
- Where: `pr-node.md:131-140`.
- The spec asks for an "importable example" using a fixture Agent. That builder now lives under `tests/test_github/test_pull_requests/test_graph/`.
- This fits the rule that fixture examples are internal test material (`pr-node.md:134-135`). Should the spec now name the maintained `examples/github` builder, or the test location?

**G-T-Q1 · question · low**
- Where: the test case factories (`IssueCase` / `PullRequestCase`).
- They are built with `model_construct`, which skips validation. This is documented and limited to trusted test values; no public input goes through it. Non-blocking.

`interfaces.md` (IF-01/IF-12) and `node-errors.md` raise no conflict. IF-12 publication stays "not executed" in the spec, which matches the probes now being archived.

## Verdicts

- **Implementation (tests and migration maps): APPROVE.** No regression coverage I compared was lost or weakened. Test counts are supporting claims, not proof.
- **Specification: REVISE.** G-S-D1 needs the specs-repo update to the evidence references. The code itself conforms to the issue and PR node contracts on the clauses I traced:
  - selection is identity, not permission;
  - the operation shape and refusal of target overrides;
  - host-resolved grants;
  - re-reading and comparing the expected digest before writing;
  - durable identity with replay;
  - unknown results are never retried;
  - the feedback ticket rules.
- **Visual and UI:** not reviewed; the frontend, live stories and your own approval remain separate.

## Not read

- **Not body-compared (names only):** the 12 PR gateway tests (`test_pull_requests/test_gateway.py`) and the interface, HTTP, admission and binding tests.
- **Not read:** the graph and component tests (`test_graph/*`), browser controls, and `test_ownership.py` beyond its imports.
- **Renamed files:** the transport delivery and mediation store tests were reported with 0/0 line changes. I took that at face value.
- **Shared support files:** `test_shared/test_migration/test_imports.py`, `import_contracts.py`, `model_contracts.py`.
- **Specs:** `interfaces.md` and `node-errors.md` only grepped, not read in full.
- **Evidence and exp:** `archive-preservation.json` and the exp contents.