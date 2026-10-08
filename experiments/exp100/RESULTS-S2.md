# EXP-100/S2: local bundle transfer result

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100).
Governing candidate: specs merge `af571c8ba460d8e7042d244ecfad87575ff07fa8`.
The base protocol was committed at `67989d4`, amendments 01–03 were frozen
through `e1c954b`, and the single recorded local run used code
`b73cda64e6ba668b2854696997ca05f6842d3786`. Independent pre-run review
approved one credential-free synthetic run at the preceding implementation
revision; the later change only bound its clean-tree preflight to the
repository with an isolated Git environment. The 22-row
[observation](observation-s2.json) has SHA-256
`8b99b90a908e6d0bdb1a5905b9008da7f52dc1e8dd00bd28804a4d115a4c7d1c`.
Git was `2.31.1.windows.1`. No model turn, Docker container, GitHub token or
provider call was used. A separate plain run reproduced all 22 rows without
overwriting evidence.

## Observed, not inferred

- A1 and A2 imported agent-created commits through bundle bytes into a
  separate bare stage seeded from the pinned baseline. The later thin bundle
  was accepted only after a host-private stage imported A1 and a host-written
  `confirmed_commit` journal entry identified it. With the baseline alone,
  M1 reported `missing_prerequisite`.
- R1, R2, R3, H1, V1, W1, F1, O1 and I1 produced their frozen reason classes.
  Reverse controls for the truncated pack, filtered/object-format headers and
  missing blob were accepted. The missing-blob fixture would have been missed
  by a rootless `git fsck`; checking connectivity from the imported commit
  rejected it at the integrity stage.
- Positive controls fired for an agent hook, local hostile remote, host global
  trace/rewrite configuration, inherited `GIT_TRACE` and replace ref. The
  verifier's corresponding stage did not execute/contact/use those inputs.
  These are architectural non-use checks on bundle bytes, not a stress test
  against simultaneous mutation of an agent's workspace.
- The evidence identity was reserved before fixtures. A unit test proved a
  failed attempt remains recorded and a second `--record` is refused. This
  recorded attempt ended `passed_local_cases`; it was not retried.

## Capability comparison at this boundary

| Surface | Direct local Git/CLI | Mediated S2 evidence | Status |
| --- | --- | --- | --- |
| `git status/add/commit` | Normal Git in isolated fixture | Agent-side fixture made two commits without a credential | Equivalent for the local fixture only |
| New branch push | A direct Git push would contact a remote | Bundle imported and classified locally; no provider call | Not compared as a remote effect |
| Later fast-forward push | Direct Git push would use remote state | Thin bundle accepted with trusted confirmed seed; no remote ref check | Partial |
| `git fetch` | Normal Git supports it | No mediated fetch | Unsupported/unverified |
| Tags, deletion, force, LFS, submodules | Normal Git has distinct behavior | Not transferred or authorized here | Unsupported/unverified |
| `gh pr`, `gh issue`, `gh run`, `gh api` | Normal `gh` behavior | No literal `gh` executed in S2 | Untested |
| Credential export and extensions | Can read a host login if available | No credential exists in fixture; no adapter executed | Not a product denial proof |
| Revocation and uncertain remote write | Direct provider effects require reconciliation | No remote mutation occurred | Untested |

The bundle candidate now has evidence for *local, staged commit transfer*.
It does **not** establish literal `git`/`gh` parity, a bounded agent-to-host
artifact handoff, production runner integration, safe concurrent replacement,
resource limits under adversarial packs, first/later remote ref leases, or
duplicate-write reconciliation. The Git remote-helper/API-proxy alternative
remains a design comparison only; it was not implemented or measured. No
transport choice or #100 acceptance follows from this result. Next, review
the evidence and decide a product-level, bounded adapter experiment before
any new live write. Keep #100 and draft #119 open until those checks exist.
