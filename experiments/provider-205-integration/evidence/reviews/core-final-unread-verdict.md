# Packet 3 review: `core-final-unread.diff`

**Bottom line:** I read the whole diff and found no confirmed blocking defect in the five areas you asked about. There are two documentation findings and five open questions. This review does not approve the PR, authorize a merge, or count as live acceptance.

## Coverage

**Read in full:** all 1609 lines of `core-final-unread.diff`. That covers:
- `RecoveryPopup` and its recovery tests;
- `PRSelectors.test`;
- the error-catalog changes;
- `ProfileEntry.tsx`, `ProfileEntryGate.tsx`, `ProfileIdentityMutationGate.tsx` and `ProfileSessionSync.tsx`;
- `profiles/README.md`;
- `test_api/headers.test.ts` and `test_entry/ProfileEntry.test.tsx`;
- `useProfileSessionActions.tsx`;
- `local_profiles/README.md`;
- the `tools/apply_langflow_skill_viewer.py` hunks (`apply_pr_controls` and the `apply_profiles` call).

**Also read as context:** the worktree's `AGENTS.md`, `feedback/pr.py`, `pull_requests/context.py` and `host/runner/service.py`.

**Not read:**
- the Langflow files at fec71dca that the installer edits (multiselect, dropdown, parameterRender, `reactflowUtils`, `use-row-data`, `InspectionPanelFields`);
- `profiles/api.ts`, `PRNodeControls.ts` and `PRNodeControls.test.tsx`;
- the backend `local_profiles/*.py` files except their README;
- `apply_langflow_local_profiles.py`, which was excluded for this packet (C-01 is with the implementer);
- the spec under `feat/410`.

**Encoding check:** characters like `â€¦` and `Ã—` in the diff are just how the diff file was decoded. A grep of the worktree files shows the correct `…`. The new `.tsx` files start with a UTF-8 BOM, which doesn't affect behaviour.

## Confirmed findings

- **D-01 (docs, low):** `local_profiles/README.md:18` says "The React entry UI is unfinished". This diff adds the full entry UI (`ProfileEntry`, the gates and session sync), so the line is now out of date.
  - **How to check:** read that line next to `profiles/ProfileEntry.tsx`.
- **D-02 (docs, low):** `profiles/README.md:1099-1101` describes the picker rows (initials avatars, left-aligned names, the divider) and the validation clearing twice, in two paragraphs that differ slightly. One of them should go.

## Questions (not defects)

- **Q-P1 (session state):** in `useProfileSessionActions.tsx:1294-1297`, `finish()` broadcasts only `if (enabled)`.
  - **Trigger:** the user signs out while the `profileMode()` check is still pending (`enabled === undefined`), or after that check failed (`enabled = false`).
  - **Effect:** no broadcast is sent, so other tabs keep the old profile's stores until their next request or a `pageshow` reload.
  - **Question:** the menu probably can't be used before `ready`. Is that guaranteed? I couldn't see the menu wiring.
- **Q-P2 (deployment and render behaviour):** the multiselect patch adds `refreshedOptions = prNode ? defaultOptions : undefined` to the effect dependencies (`[value, refreshedOptions]`).
  - **Risk:** if upstream builds `defaultOptions` as a new array on every render, the effect runs every render. If that effect sets state, this could loop or reset the user's selection.
  - **Question:** I didn't read the upstream multiselect at fec71dca. Is `defaultOptions` a stable reference?
- **Q-P3 (deployment):** `apply()` runs `from apply_langflow_local_profiles import apply_profiles` (diff line 1604). That only resolves when `tools/` is on `sys.path`, which is true when the file runs as a script.
  - **Question:** do any tests or entry points import this module as `tools.apply_langflow_skill_viewer`? If so, that import would fail after every PR overlay edit has already been written, the same partial-write class as C-01.
- **Q-P4 (PR picker, low):** `parameterRenderComponent` uses `useFlowStore.getState()` during render, which doesn't subscribe to the store. `prFieldTemplate` and the placeholder can therefore show stale values until something else triggers a re-render. This affects display only; dispatch is unchanged.
- **Q-P5 (profile state, low):** `reconcile()` (`ProfileEntry.tsx:633`) matches saved profiles with an exact, case-sensitive `item.name === name.trim()`, but the registry enforces uniqueness case-insensitively.
  - **Question:** can the server normalise or return the name differently from what the user typed? If so, the check reports "not confirmed" for a profile that was actually saved. That fails safe (it says to check the list, never to create again), but it would mislead the user.

## Answers to the packet questions

- **Login/profile session state:**
  - Entry clears the PIN on success and failure, broadcasts, then calls `location.replace("/")` to load a fresh document.
  - A PIN that isn't six digits is refused locally as `profile_pin_rejected` (login failed), with no request sent.
  - A 401 response makes exactly one fetch (tested).
  - A failed identity-gate check hides the identity editors.
  - The session check exposes only `{authenticated, profileId}` (tested against `store_api_key` leaking).
  - Only Q-P1 is open.
- **Model refresh/dispatch:** the catalog refresh runs only through `onReady` after a user-initiated start; none happens on the initial poll, after a failure, cancellation or the deadline, and there is no second start. Nothing in the profile code dispatches model work. The labels "Refresh list" button only re-submits the field value.
- **Private-context disclosure:**
  - The broadcast message carries only a type and a random tab ID.
  - Entry errors show catalog text without technical details (tested).
  - No PIN is persisted.
- **PR picker/port behaviour:**
  - The dropdown disables Enter for PR nodes, so typing can't create a typed identity.
  - Only the direct PR ↔ Agent feedback edge bypasses the cycle check.
  - The legacy `operation` port is refused, consistent with `pr.py` (`context_input_name` → `pr_context`).
  - Q-P2 and Q-P4 are open.
- **Deployment failure:** every `replace_once` anchor is unverified because I didn't read the upstream files. Q-P3 and C-01 remain open.

## Verdicts (this packet only)

- **Code:** No blocking defect found in the scope I read, conditional on Q-P1 to Q-P3. This is not a whole-PR approval.
- **Visual:** No verdict. The profile picker, create, PIN and sign-out screens and the recovery spinner were not captured. The earlier APPROVE for Skill, Prior Run and the PR layout still stands.
- **Docs:** Changes requested (D-01, D-02).
- **Spec:** Not reviewed in this packet.
- **Acceptance:** The tests here are fixture and unit tests, so they don't establish the real browser stories (cross-tab sync, sign-out, entry). Live acceptance is still outstanding.

**Reviewer status:** this packet is reviewed with the findings above. The installer anchors, `api.ts`, the backend profile modules and C-01's fix are still unreviewed. No merge or issue closure is authorized.