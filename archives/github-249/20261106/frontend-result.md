# PR249 packet 3 at head `9d8793a2`: frontend, installer, maintained example and spec correction

The viewer refactor, installer change and both spec fixes look correct for what I read. Two things are not done: the live read-recovery result is still pending, and the PR's material test bodies and operation paths remain unverified. So none of the verdicts below approves the whole PR.

## What I read

- **Rules:** the root `AGENTS.md`, searched for the fixture-presentation, approval and ownership rules (lines 17–68), not read in full. I did not separately open a CONTRIBUTING file.
- **`frontend.diff`, lines 1–847 (all frontend and installer hunks):**
  - the new `github/` tree: `interface/InspectionError.tsx` and its test, the issue and pull_request viewer modules (selection, models, index and the moved modals), and the READMEs;
  - the `node-error-catalog.json` additions and the two edited entries;
  - the change to `nodeErrors.ts` (`structuredFailure`) and its tests;
  - the import path updates in `upstream.patch` and `agents.patch`;
  - the `tools/apply_langflow_skill_viewer.py` hunk.

  I read the migration hunks in packet 2.
- **`builder-fix.diff` in full**, plus the maintained `examples/github/README.md` and `build_flow.py`.
- **`spec-links.diff` in full**, with `pr-node.md`, `validation.md` and `langflow-node.md` as context.
- **Images (four, all opened):** `real-issue-viewer.png`, `real-pr-viewer.png`, `real-issue-offline.png`, `real-pr-offline.png`.

## Findings

**G-F-D1 · defect · medium · introduced**
- Where: `node-error-catalog.json:509-529`, the entries for `unauthorized` and `invalid_request`.
- These are shared codes that the runner and Agent use too, not only GitHub. The PR rewrites their text in runner-neutral "local service" wording:
  - For `unauthorized`, the runner-specific recovery advice ("check runner authentication and the configured runner address") is gone.
  - For `invalid_request`, the old warning not to "start another request until any existing execution is accounted for" is replaced by "inspect the existing operation result", which only covers an attempted *update*.
- Effect: a runner `invalid_request` now shows GitHub-shaped recovery advice and loses its "account for the existing execution" wording. The no-unsafe-retry test (`nodeErrors.test.ts:791`) covers only four runner codes, so it does not catch this.
- This changes shared Agent and Skills copy from inside the GitHub PR. Fix: add GitHub-specific codes, or have the Agent/Shared owner agree the neutral wording.

**G-F-Q1 · question · low · introduced**
- Where: `tools/apply_langflow_skill_viewer.py:840-844`.
- `copytree(overlay/"github", …, ignore=README.md)` also deploys `*.test.tsx` files, including `InspectionError.test.tsx`, which is marked "Internal presentation controls", into the production `src/modals/github`.
- That is presumably how the 572 Jest count is reached, and Vite will not bundle unimported tests. But the TypeScript build now type-checks them too. Is this intended, or should tests be excluded from the deploy?

**G-V-Q1 · visual question · low**
- Where: both offline images, top right of the error card.
- The copy control shows a ✓ glyph on an error panel. If that is the "copied" state left over from the capture script clicking Copy, it is fine. If it is the resting state, it reads like a success mark on a failure.
- The captures do not establish which. Please confirm the resting icon.

**G-V-S1 · visual suggestion · low · mostly pre-existing**
- Where: both viewer modals.
- The modal's nav repeats its own "Issue viewer" / "PR viewer" button.
- The "Read:" timestamp shows raw ISO with microseconds.
- Below the content there is about 400px of empty, fixed-height space.
- The error card uses the same neutral border as content, with no alert colour or icon. Hierarchy comes from bold text alone.

**G-S-Q2 · spec question · low**
- Where: the `pr-node.md` correction.
- It says the maintained builder "accepts real selected resources and an optional existing Agent feedback path".
- That matches `build_flow.py:41` (feedback only for PRs, and only with a runner URL, skill id and revision all supplied). This is a confirmation, not a defect.

## What checks out

- **Selection identity and stale replies:** the selection logic moved unchanged (`selection.ts` matches the deleted inline code). The abort/key/reload effects and the identity-mismatch check are unchanged. A client-side identity mismatch now falls back to the read-only fallback with that fallback's own diagnostics.
- **Error admission and redaction:**
  - Only `data.code` and `data.detail.code` are read. Unknown codes and the generic `github_*_unavailable` codes become read-only text that says "repeats only this read".
  - Copied error text excludes other fields (`do-not-copy`), and credential-shaped codes are scrubbed (these are fixture-based unit controls).
  - `structuredFailure` only accepts the versioned `laomedo.github-{pr,issue}.v1` envelopes, and only with `failed` or `unknown` status. Successful operations, nested body content and plain text are not treated as errors.
  - The 2 MiB parse cap covers a maximum body under sixfold escaping.
- **No blind retries:** the new `*_write_unknown` and `pr_feedback_ticket_invalid` messages say to inspect the remote state before authorizing another operation. Refresh only repeats the read, and both viewer requests carry no `operation` field.
- **Installer:** it deploys the defining `github/` tree, and the `upstream.patch` and `agents.patch` imports point at `@/modals/github/{issues,pull_requests}`. Both index files export `nodeKind`, so the existing callers still resolve. No Skills runtime code changed; `skillFilesModal` is referenced unchanged.
- **Builder fix:** the `import langflow` that initializes LFX in a fresh process is minimal. The new subprocess test (`test_example.py`) checks a one-node, no-edge graph and its selected choice for both kinds, and does not execute anything. The grammar fix (G-B-S1) is done.
- **Fixture boundary:** the maintained example uses production components and real resources. Fixture controls are named as test-only, so no unauthorized fixture demonstration is presented.
- **Live captures (supporting, not acceptance):**
  - Issue #23 and PR #24 show exact titles, state, labels, head → base, draft/merged status and both timestamps.
  - Text wraps without overflow, and Open in GitHub is present.
  - The offline cards have a clear title, a cause stated as not established, read-only recovery, and Technical details collapsed. That collapsed section means the exact code shown in these captures is unconfirmed.
  - These images do not prove recovery after an outage.

## Spec correction (G-S-D1 and G-S-Q1)

`spec-links.diff` fixes the issue.
- All eight stale `validation.md` references now point to `archives/github-244/files/...` at `714db418`. A new paragraph says the move preserves bytes and limitations and does not establish current acceptance. No test counts, results or limitations changed.
- `pr-node.md` now separates the internal fixture builder (`tests/.../test_graph/builder.py` at `9d8793a2`) from the maintained real-resource builder. It explicitly says generating a graph "does not execute or validate it". The fixture-approval and real-demonstration rules are unchanged.

Limit: I checked that the link paths look right, not that each file exists at `714db418`. Per the brief, I did not fetch exp; the 49/49 archive check covers the bytes.

## Verdicts (this packet only)

- **Implementation (frontend, installer, example, builder fix): REVISE**, for G-F-D1 (the shared catalogue copy). Everything else here is acceptable.
- **Specification:** the G-S-D1 and G-S-Q1 correction is **APPROVE**.
- **Visual: no blocking defect seen in the inspected states (open G-V-Q1/G-V-S1); not an approval.** The inspected states are loaded issue, loaded PR and the two offline cards. This is not full UI approval: the outage-recovery result and your workflow acceptance are still pending.
- **Whole PR: not approved.**

## Not read or not verified

- **Packet-2 test bodies that still warrant review:**
  - `test_pull_requests/test_gateway.py`, 12 tests: compare against the old `test_live_github_pr.py` bodies, especially head/base/merged refusals and partial label effects;
  - `test_interface/*` client, HTTP, admission and binding tests;
  - `test_graph/*` feedback-loop tests: a single Agent invocation, refusals and unknown outcomes;
  - `test_ownership.py`.
- **Not needed:** transport and mediation test files renamed with no line changes.
- **Not read:**
  - `examples/graph.py`, `components/laomedo/github_*.py`;
  - `NodeErrorNotice` beyond its test;
  - `ErrorExplanation` and `CopyIcon` sources;
  - `real-inspection.json`;
  - `tests-spec-result.log`;
  - CONTRIBUTING and feature READMEs beyond the ones listed.
- **Not verified at the current head:** the full TypeScript check, the wheel, live mutation, uncertain delivery and live outage recovery.