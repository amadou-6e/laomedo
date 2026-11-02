# GitHub workflow verification

Recorded on 2026-11-02 for [PR #248](https://github.com/amadou-6e/laomedo/pull/248).
These are real local browser and GitHub results, separate from the internal
provider-double tests and earlier archived experiments.

## Tested environment

- Product code and frontend: `b41fd92309ad74994262cdbe9373219300581127`.
  The example's later position-only adjustment places the independent Skill below
  the PR without overlap; it does not change component code, connections or inputs.
- Windows, Python 3.12, Langflow frontend pinned to
  `fec71dca901949c09ed4d63315804337cd2eb13d`, headless Edge at 1600 × 1100.
- Installed wheel SHA256:
  `7092b23467d3459c0f0657088b4e2a5df8a5c7357005dcaf32fafdb7a68ef025`.
  All 286 packaged files matched the source and installed bytes. The restarted app
  used that wheel. Background services retained their recorded `4a936b4` origin;
  all 286 package files and four relevant component sources were byte-identical
  to the tested final sources.
- Real original Codex Agent using the existing dedicated local login volume.
  The supported explicit trusted-image override was
  `sha256:73ad6bbdfa6a8c14ecb50cf4276c013184b0befa75bb7facdab38977e37bd738`.
  This does not establish acceptance of the default image configuration.
- Actual repository: `ga84jog/laomedo-exp104-disposable-20261007`.
  No intercepted routes, fake provider or synthetic model result.

## Observed stories

| Story | Result and evidence |
| --- | --- |
| Select and inspect an Issue | Real Issue #23 discovered, selected and read; 1.061 s component run. Actual populated viewer and exact GitHub link opened with no model call. |
| Select and inspect a PR | Real PR #24 discovered, selected and read after its update; 1.229 s component run. Actual populated viewer and exact GitHub link opened with no model call. |
| Repository changes and refresh | Both pickers cleared after a repository URL change. Refresh did not select the first result; refreshing an explicit selection retained its exact number. |
| Issue operation | After explicit owner approval, native Load JSON → Issue.Operation updated Issue #23 to `GitHub issue operation verified` with existing `bug` and `documentation` labels. The real graph completed the operation in 4.189 s; an independent read and one confirmed `issue_update` effect verified the change. Its body and open state stayed unchanged. The grant was revoked and the incoming operation removed afterward. |
| All-label filtering | The actual scoped service and Issue picker both returned only Issue #23 for `bug` AND `documentation`. The PR picker returned the actual empty result for the same pair. Both recovered to the unfiltered explicit selection. |
| Stale saved selection | Saved graph inputs deliberately paired an actual selected Issue/PR with a filter absent from its current GitHub labels. Running revalidated real data and refused with `selected_issue_no_longer_matches` / `selected_pr_no_longer_matches`. Both recovered through the real label control and picker, then read successfully. No provider mutation or model call was used. |
| Missing PR selection | Refused in 0.970 s with `selected_pr_required`. Descriptive details and the stable code were copied through the real clipboard; the card stayed within the viewport and dismissed. |
| PR feedback without authority | The actual host returned `pr_grant_unavailable` before Agent dispatch. Error details displayed its explanation, recovery and safe diagnostic code, including after grant revocation. |
| PR → Agent → same PR.Operation | One original Codex Agent run completed; the full workflow took 19.519 s. The host recorded one confirmed `pr_node_update` effect. An independent GitHub read confirmed the exact title `Original Codex Agent feedback verified`, with body, labels, open state, head commit and base unchanged. |
| Saved controls across browser restarts | The later independent Edge launch restored the saved actual model and effort selections. This is graph persistence, not acceptance of an external account/session-management product. |
| Skill history failure and recovery | The preview initially omitted the operation/history service connection: file inspection worked, but Retry repeated HTTP 400. After connecting the actual service to the same registry, Retry in the already-open dialog returned HTTP 200 in 307 ms. The imported Skill correctly showed no operation history; it still loaded after a page reload. No Skill edit or graph dispatch occurred. |
| Cleanup | Native controller and lease cleanup were confirmed. The exact owned container was absent. The scoped write grant was revoked and its private binding cleared. Other sessions were not changed; read-only preview services remained available for owner inspection. |

The real workflow's graph execution was
`d1bbc767-715f-4d33-97b1-62c17904542c`; its completed native run was
`3efa5ce8-63a7-4030-b1a8-dcb68c591b6f`. The selected model was advertised by the
actual runner (`gpt-6.1-sol`), with `low` selected in the graph. Native effective
effort was not reported; it is not inferred from that selection.

![Actual Issue viewer](issue-viewer.png)

![Actual updated PR viewer](pr-viewer.png)

![Actual graph with PR feedback and independent pinned Skill](graph.png)

![Actual refused PR operation with safe technical details](grant-refusal.png)

![Actual missing-selection error and diagnostic copy control](missing-selection.png)

![Actual Skill viewer after history service recovery, with no operations yet](skill-history.png)

## Verification boundaries

The 151 GitHub controls passed against the exact installed wheel outside the
checkout (five environmental skips); 368 affected frontend tests passed. Earlier
source and installed full discovery each passed 1118 tests with their recorded
environmental skips, and 14 optional Langflow modules exited successfully.
Final code-head CI passed all eight checks, including Black. These controls
support the real stories above; they do not replace them.

The real read checks reported no page errors, and served JavaScript/CSS bytes
were checked against the exact build. The initial post-restart check reached the
app before its approximately 100-second startup finished; subsequent real checks
passed. Earlier private browser assertions were corrected for native placeholder
wording and modal/navigation timing, without changing provider responses.

The first Issue-operation setup supplied an unconnected value; it performed a
read and recorded no effect. Independent reconciliation confirmed no remote
change before the same request identity was supplied through a real native
JSON output connection. Only that connected attempt performed the approved edit.

Uncertain writes and delivery-loss recovery retain internal regression coverage;
they are not claimed as newly verified live paths here.
No uncertain write was blindly resent. PR creation and an Issue feedback cycle
remain outside the implemented contract. Agent/ACP restructuring is deferred.

The requesting owner's final graph inspection and user-story validation are
pending. This record is not merge approval or a claim of complete browser
acceptance. Private raw workflow events, credentials, profiles, tokens and runtime
databases are deliberately excluded from the repository.
