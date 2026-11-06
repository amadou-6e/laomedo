# nonpython-agent-documentation-2: conservation report (read-only)

**All 23 PRs stay on HOLD.** This report approves nothing. Browser, provider and owner gates are separate.

Nearly every original change survives. The only concrete break is one README pointing at a deleted contract file.

I read all 21 entries (lines 1-744) in full. Three are exact blobs; for those I reused the hash match and checked the current code binding.

## Inspected ranges (final worktree)

- **Read in full:** `src/laomedo/agents/activity/README.md:60-73`, `workspaces/skills/README.md:34-50`, `pyproject.toml:1-27`.
- **Pattern checks across `src/laomedo/agents/**/*.md`:** 33 distinctive object, method and code names from the packet.
- **Other checks:**
  - `claude/auth/README.md`: `py-docker`, the `49652f4` pin and its draft status;
  - `tests/contracts/activity-projection-3508b7aee.json` (absent);
  - `tests/test_agents/test_activity/test_envelope.py:11-107`;
  - which tests consume the retained-probe loader.

## Dispositions (versions grouped by path)

| Old PR / path | Original change | Disposition | Current evidence |
|---|---|---|---|
| 216 `interface/output/README.md` (exact) | Output-contract leaf | **PRESERVED** | Unchanged bytes. |
| 216/219 `orchestration/README.md` (2 versions) | `AgentHandoffController` methods; the `AgentHandoff`/`Handoff*` value vocabulary and envelope rules | **PRESERVED**, rewritten | `orchestration/README.md:21-22`. |
| 216/232 `workspaces/README.md` (2 versions) | `AgentWorkspace`/`WorkspacePaths`/`WorkspaceSnapshot`; the 232 split into `baseline.initialize` and `cleanup.remove_owned_tree` | **PRESERVED** | `workspaces/README.md:15-16`, `:34-35`. |
| 232 `workspaces/skills/README.md` (added) | `_exclude`/`install`/`verify`; `AgentSkillBinding`/`SkillGitExclusion`; catalogue guards for three producers; the EXP104 loader | **PRESERVED**; the loader text is superseded | `:13-14`, `:37-46`. The `retained_native_probe_loader.py` paragraph is replaced by the settled `tests/support/retained.py`. `:48-49` names the remaining gap with the exp campaign dependencies. |
| 219/227 `agents/base/README.md` (2 versions) | `PreparedRunRecord`, `PreparedWorkspaceState`, `AgentSkillBinding`; `FailureObservation`/`AttemptFailureRecord`, `_retain_attempt_failure`, `cleanup_source` semantics, `CreateNotSentDeadlineError` | **PRESERVED** | `base/README.md:35`, `:37`, `:49-50`, `:56`, `:62`, `:69`. |
| 219 `artifacts/README.md` | `ArtifactReference` | **PRESERVED** | `:4`, `:15`. |
| 219 `interface/README.md` | `RunnerStatusRecord`/`AgentRunReference`, `PrecheckEvidence`, `AgentSubmission`, `AgentDispatchResult`; `JsonValue` preservation | **PRESERVED** | `interface/README.md:36-42`. |
| 220/233 `activity/README.md` (2 versions) | `ActivityAttemptRecord`, `TokenUsage`; the `ActivityProjection` envelope and its two payload orders | **PRESERVED**, with one dangling reference | `:32`, `:38-40`, `:47-67`. Behaviour is tested in `test_envelope.py:18-107`. `:69-72` cites a missing contract file. → D1 |
| 220 `claude/activity/README.md` (exact) | `ClaudeTelemetryEnvironment` | **PRESERVED** | `:23`. |
| 220/227 `opencode/README.md` (2 versions) | `OpenCodeRuntimeIdentity`; exact resource closure, `opencode_container_cleanup_unverified`, `opencode_owned_resources` | **PRESERVED** | `:39`, `:54`, `:58`. |
| 220/233 `opencode/activity/README.md` (2 versions; current is the PR233 exact blob) | `OpenCodeTokenUsage`; the shared envelope | **PRESERVED** | `:12-13`, `:21-22`. |
| 225 `claude/README.md` | Discovery and preflight timing versus the 75 s and 65 s waits | **PRESERVED** | `claude/README.md:20`. |
| 225 `claude/auth/README.md` | Mirror repair: `ClaudeAccessLoginRecord`, 90 s + 20 s policy, `LAOMEDO_CLAUDE_LOGIN_STATE_DIR`, discovery/preflight timing table, `npipe` admission, `py-docker 49652f4` | **PRESERVED** | `:12-25`, `:30`, `:52`, `:70`, `:74-76`, `:107-108`, `:133`, `:147`. The pin matches the runner extra in `pyproject.toml:19-20`. → S1 |
| 225 `claude/auth/resources/README.md` (exact) | `write_login` container protocol | **PRESERVED** | Unchanged bytes. |
| 227 `codex/README.md` | Failure finalization: `lease_service_lost`, `LeaseLossObservation`, `LeaseCleanupObservation` | **PRESERVED** | `codex/README.md:34-43`. |

## Findings

**nonpython-agent-documentation-2-D1: the Activity README cites a retired contract file**
- **Applies to:** spec/docs.
- **The claim:** `src/laomedo/agents/activity/README.md:69-72` says "the retained `tests/contracts/activity-projection-3508b7aee.json` records old projector bytes and Git blob provenance".
- **The reality:** that file does not exist. The matching compatibility control is gone, which fits the cleanup of obsolete proof JSON recorded in documentation-3.
- **What still covers behaviour:** the envelope tests (`test_envelope.py:48-107`) check field order, omitted vs empty diagnostics, and preservation.
- **Fix:** remove or reword the paragraph.
- **Pattern:** same as documentation-2 D1 and metadata-3 D1.

**nonpython-agent-documentation-2-S1: the Claude auth README still reads as a status log**
- **Applies to:** docs.
- **Detail:** `claude/auth/README.md:12-25` and `:74-76` still say "implemented draft, live validation pending" and "real copying is blocked until…". That is status and chronology rather than declarative contract text, which goes against the declarative-README preference.
- **Uncertainty:** whether the py-docker log-driver validation has since happened. If so, the text is also out of date.

## Leftovers / UNVERIFIED

- Exact wording beyond the matched names in each README. I confirmed the concepts and identifiers survive, not every sentence.
- Whether `test_envelope.py` reproduces the old projector's byte order (it isn't compared to old bytes).
- The current state of the py-docker log-driver validation behind S1.