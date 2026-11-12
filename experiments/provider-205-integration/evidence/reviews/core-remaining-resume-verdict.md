# Develop integration, packet 2: remaining core hunks and visual check (frozen d3d06e3a; final head 97ea2c3c)

The previously pending rate-limited request is closed out by this verdict; nothing from it carries forward.

I re-read `AGENTS.md` in full this turn, including the new Test lifecycle and UI change handoff sections. The merge resolution is sound in everything I read, and the captured views show Skill, Prior Run and the new PR node rendering as intended. I found one low-severity defect in a frontend overlay tool (C-01). I still read only part of the frontend and profile code, so core code is **INCOMPLETE**. This is not whole-PR approval and not live acceptance.

## Questions from packet 1

**Q1: closed.** You report that `Graph._replace_conditional_exclusions` exists in the installed lfx Graph and in the pinned upstream source at `base.py:1523`. I'm taking that from your evidence file, which I didn't open myself.

**Q2: closed, and I verified the caller.**
- `feedback/pr.py:230-236` refuses with `pr_agent_loop_invalid` when there is no feedback edge, when there isn't exactly one start edge, or when that edge doesn't target the feedback agent.
- `github_pr.py` reaches `agent_operation` only through `_roundtrip`, which runs only after `feedback_edge(self)` returns an edge.

**Q3: still an open edge case.** I'm not escalating it.

## Confirmed finding

**C-01 (Low): `tools/apply_langflow_local_profiles.py` can leave a half-patched frontend.**
- **Trigger:** one of the later anchors is missing from the upstream checkout: auth context, password gate, profile picture or tracking.
- **Mechanism:**
  - `routes.tsx` and the account menu are checked first and written last;
  - but the header, logout, auth-context, password-gate and GeneralPage files are written one by one, before the later anchors are checked (`:2811-2872`).
- **Consequence:** the tool exits with an error after it has already modified part of the checkout. A plain re-run then fails differently, because the edited anchors no longer match.
- **Impact today:** low. It applies only to the pinned fresh overlay of fec71dca, where your build shows every anchor exists.
- **Fix:** check every anchor first, then write all the files.

## Verified from what I read

**Local profiles: admission, authentication and boundary.**
- Admission checks the database read-only before anything runs. It refuses all of the following:
  - auto-login, sign-up, external auth, or an API key in the environment;
  - a database URL other than the expected one;
  - a symlinked database;
  - a schema or alembic head that doesn't match;
  - more than one superuser;
  - the system actor having an API key or using the default password.
- The system actor gets a random in-memory password.
- `LocalProfileAuthService` blocks the system name and superusers in login, token creation, token checks and API-key checks.
- The ASGI boundary on the profile, login, logout, refresh and users routes requires:
  - an exact loopback `Host`;
  - same-origin `Origin` and `Sec-Fetch-Site`, with duplicate headers refused;
  - an `Origin` header on every write;
  - no mutation of user records.
- PINs are `SecretStr` values, excluded from dumps, compared in constant time, and never sent back.
- Registration runs under a lock and delegates to upstream `add_user`. Uncertain outcomes return `profile_creation_unconfirmed` rather than being retried.
- The browser `api.ts` keeps only cookies set by upstream and puts no token into UI state. After login it confirms the identity through `whoami`.

**Profile mode and launch.**
- Profile mode is opt-in: `create_app(profile_runtime=...)` is called only from `tools/start_local_profiles.ps1`.
- `AppLauncher` keeps auto-login and passes no profile runtime, so the two develop launch paths stay separate rather than conflicting.
- `/profile-mode` exposes only a boolean.

**Runner recovery (`RunnerRecovery.tsx`).**
- An automatic model refresh happens only after a start that you initiated is confirmed. It has a 2-minute deadline, and no second start is sent.
- The start button is hidden while waiting for the catalog.
- `unmanaged` now shows guidance to restart the app with its runner configuration.
- Recovery and health still go through the shared endpoint.

**PR controls and agent inputs.**
- Field order is Repository URL, State, Labels, PR, then the context port.
- `discovery_status` is hidden, and only three fixed status strings are shown, so arbitrary text never appears. The test checks that a token-like string is suppressed.
- The canvas accepts only the two-node PR ↔ Agent feedback connection.
- The Skill and Agent filters in `RenderAgentInputParameters` are unchanged, and the PR filter and ranking are added alongside them.

**Other changed files:**
- `langflow/settings.py` adds the default Codex runner URL; it is hidden from `repr` and dumps.
- `viewer.py` accepts `merged` as a PR state.
- The changes in `skill_editing.py` and `viewer.py` only move imports to new owners.

## Visual verdict, from the three combined-build captures

| Capture | Status | What it shows |
|---|---|---|
| Default (`preview-default.png`) | **APPROVE** | <ul><li>The Skill node is compact: Source, Skill, the Operation port, Advanced collapsed, and no Edit Request.</li><li>Both Codex nodes show Task as an input with a port, which matches the new Message/Data input.</li><li>The resume node shows Prior Run, connected from Run Reference.</li></ul> |
| Advanced (`preview-advanced.png`) | **APPROVE** | Revision and Base Commit appear under Advanced settings. The layout is identical to the earlier approved capture. |
| PR (`pr-preview.png`) | **APPROVE** for layout | <ul><li>Fields appear in the order Repository URL, inline red discovery error, State (open), Labels and PR (both "Connection unavailable"), then the PR context port.</li><li>There is a single PR output.</li><li>Nothing overflows at 200%.</li></ul> This shows unconfigured discovery only, not live GitHub. |

**Not captured, so not visually approved:**
- the profile entry, picker and switch screens;
- the recovery popups;
- PR states for loading, no matches and success.

## Checks

As you reported them (I didn't open these logs):
- final head 97ea2c3c: all five CI checks pass;
- local suite: 1595 passes and 13 skips;
- 80 frontend tests pass.

The test-binding fixes in f38e4b70 belong to the separate tests packet and aren't reviewed here.

## Not read, and not covered

**`core-remaining.diff`:**
- `:1-242`: the frontend README, RecoveryPopup and its test, and the RunnerRecovery test;
- `:583-1445`:
  - the PRSelectors test and the PR README;
  - the node error catalog and its test;
  - `ProfileEntry`, `ProfileEntryGate`, `ProfileIdentityMutationGate`, `ProfileSessionSync`;
  - the profiles README;
- `:1633-1994`:
  - the headers test and the entry test;
  - `useProfileSessionActions`;
  - the local_profiles README;
- `:2891` to the end: the `apply_langflow_skill_viewer.py` hunk.

**Other:**
- the associated tests you named (`tests/test_authentication`, the PR graph tests, `test_app_launch`);
- the imports, tests and docs packets.

## Verdicts

| Area | Verdict |
|---|---|
| Core code | **INCOMPLETE**. There are no wrong bindings or lost controls in the parts read. C-01 is a low-severity fix. |
| Visual | **APPROVE** for Skill default and Advanced, connected Prior Run, and the single-port PR layout. Profile and recovery screens are not captured. |
| Whole PR | Not approved. No live acceptance is inferred. |