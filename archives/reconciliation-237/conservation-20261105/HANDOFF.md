# Conservation review continuation

The reviewer workflow was merged in amadou-6e/my-skills PR #36 at b1495917.
The same dedicated Claude conversation resumed the existing Laomedo audit.
This is a preservation review, not product acceptance or permission to retire PRs.

Owner heads were verified unchanged against GitHub on 5 November 2026:
Shared #255 `570cac84`; Skills #254 `4dee127d`; GitHub #249 `3dce778b`;
Agent #250 `a29ce61b`. Develop remains `37dc9aa9`. All four worktrees are clean.

Runtime packets 1-3 retain their previously recorded limited coverage.
Runtime packets 4-6 are now COMPLETE. Packet 4: all 27 headers/1,171 lines inspected;
no preservation gap or defect found. Its two low suggestions concern future
serialization-order assertions and noncanonical nested key order. The report
identifies its exact inspected scope, source/test evidence and limitations.

An earlier unverified OpenCode cleanup claim has concrete current coverage in
`tests/test_agents/test_runtime/test_failure_finalization.py`; the actual Claude
resume replay control is in `tests/test_agents/test_claude/test_session.py`.
These must be inspected as evidence, not replaced by duplicate tests or assumed
real-provider acceptance. The narrow default-configuration assertion gap remains
under examination.

Packet 5 covers 46 headers across PRs216/218/220/222; packet6 covers20 across
PRs222/224/226/228. Neither found a runtime gap or defect. Their optional regression
suggestions remain explicitly nonblocking.

All eight original Activity projector captures now match the restored literals
byte-for-byte, including input/kwargs/key order and SHA256. The committed proof
is internal literal fidelity, not a new provider/browser result. Earlier reviewer
partial-decoding limits are retained in the historical packet report.

Next: test packets 1-5 (in progress), the non-Python path/version review,
focused verification of restored #217/#233 assertions, unresolved contract triage,
and the final per-old-PR conservation judgment. None of the 23 old PRs is retired
or merged. Feature/provider/browser/user-validation gates remain separate.

The 4 November archive and its exact historical bundles remain authoritative for
prior evidence and recovery. No credentials, runtime profiles or raw private
review transcripts are included here. The visible implementation stays on clean
develop; unrelated worktrees and user changes in specs are preserved.

Test packet1 is complete (56 headers). Five Agent-owned regression gaps are
confirmed for batched restoration. T1-D4 is rejected: the existing stronger
installed-package/current-source guard is present in Shared255 and final1eb10a1f.
It was executed against the actual installed wheel, isolated mode, and passed
without skips. The reviewer missed its renamed method; no duplicate test is added.
Tests2-5 and non-Python coverage remain in progress; all23 remain HOLD.

Agent250 is now244c0c74da716d7c36ba7c826565ac5df7e9c506, pushed and draft.
All five confirmed Test1 gaps were restored in six test files:124lines added,
1removed. No runtime source changed. All86affected internal controls pass with
zero skips; all128installed Agent Python modules matched owning source.
The stale-wheel guard already existed and passed from the installed artifact.
Affected pinnedBlack passes; both hosted project-wide Black checks pass.
Local whole-project Black was interrupted after prolonged CPU use; no local
whole-project pass is claimed. See hosted-checks.json for exact latest CI state.

Claude Test2 stopped at the five-hour limit, reported reset02:40 Europe/Berlin.
The dedicated transcript was inspected only after its pending offset; it contains
a rate-limit refusal and no completed review. The pending digest/configuration
and decision are preserved in finding-ledger.json. Do not retry blindly or start
a fresh reviewer conversation. The prepared first focused recheck for the five
restored controls is private under resume-20261105/agent-controls-recheck-request.md
and its exact diff. After availability returns, inspect/resolve that pending
request explicitly, recheck the batch, then resume tests2-5 and non-Python review
with the updated Agent head. All23old PRs remainOPEN/HOLD. No issue changed, no
Laomedo PR merged, no new model/provider/browser run or credential copy occurred.
The only merge authorized/executed in this continuation was my-skills36b1495917.
