# Old refactor checkpoint conservation - in progress

This exp checkpoint preserves the exact heads and bases of all 23 old PRs:
#213, #214, #216-#234, #236 and #238. It does not authorize their retirement or
merge. The old stack remains open and must not be merged separately.

## Exact recovery independent of old branch names

The 2.1 MB Git bundle contains all 23 PR head references and the base endpoints
not already reachable from exp. Its one prerequisite, 5ffab075bbab50e195a3c8a375a83dff55a70fea,
is already in exp history. A fresh bare repository fetched ONLY exp plus this
bundle: all 69 head/base/merge-base tree identities, all 23 merge bases and full
Git fsck passed. See the bundle manifest and fresh verification record.

From an exp checkout, verify and fetch the bundle without changing any branch:

```powershell
git bundle verify archives/reconciliation-237/checkpoints-20261104/old-refactor-checkpoints.bundle
git fetch archives/reconciliation-237/checkpoints-20261104/old-refactor-checkpoints.bundle 'refs/archives/checkpoint-audit-20261104/*:refs/archives/checkpoint-audit-20261104/*'
git show refs/archives/checkpoint-audit-20261104/pr-234-head:frontend/langflow-skill-viewer/SkillHistory.tsx
```

PR metadata records exact merge-base/head pairs so every original own-diff can be
reconstructed. Archive preservation is not active production regression coverage.

## Concrete recovery so far

The audit found missing lease HTTP tests, Skill listener credential/service
isolation and safe-error tests, lease model/redaction/cleanup callback tests,
provider command failure and pending-receipt controls, CLI/digest/routing checks,
LF/CRLF byte preimages, actual pinned Langflow hashes, stale graph refusals and
activity completeness. They were ported into their concern owners and pushed.
The exact test-only recovery received a bounded independent Claude approval;
its seven installed-package selections, six provider controls, registry bytes,
GitHub bindings and three optional Langflow modules passed. The affected Agent
source run passed 554 tests with four skips. These are internal regressions,
not live model/provider or user acceptance. See review-summary.json.

Further own-diff inspection found checkpoint234 UI changes missing even before
the prior integrated-tip comparison: descriptive inline inspection errors,
catalogue entries, native timeout descriptions, credential-prefix redaction,
and canvas retention during background build-history reads. Their integration
with the newer editable Skill workspace is pushed as explicitly UNVERIFIED work
on Shared1fa9b288 and Skills57da9d79; combined431bf6a8. Python coverage guards
pass. Frontend compilation, restored UI tests, complete real browser paths,
independent code/visual review and owner validation remain pending.

## Limits and retirement gates

The initial comparison covered 1686 path versions from each PR's own diff.
The binding comparison contains repeated versions and class/method rows: its
144 normalized candidates and 807 changed rows are triage, not a semantic or
assertion-equivalence certificate. It predates the new recoveries. The earlier
2996-path/6218-definition integrated-tip ledgers could not prove that intermediate
checkpoint assertions survived; this audit found counterexamples.

retirement-status.json maps every old PR to its owning replacement and keeps
retirement NOT_YET_VERIFIED. Do not turn archive availability, green CI, a matching
method name or the bounded test review into an all23 approval. Keep existing
full feature/provider/spec/UI/owner gates. No old PR was closed or merged here.
Other PRs such as252/168 and58/71 remain outside this selected23 audit.
