# PR250 corrections and integration packet at head `bb331f54`

A-R-Q1 is resolved. The Claude copy serialization keeps the deadline, receipt and credential guarantees. A-I-G1 is mostly closed, with one dangling link and one gap in what the audit can detect. The new findings are low-severity except one visual question about contradictory recovery copy (A-V-Q2). This is not approval of the whole PR.

## What I read

- **The four correction diffs in full:** `resume-fix.diff`, `recovery-fix.diff`, `final-settings-fix.diff`, `claude-copy-fix.diff`.
- **Callers and source:**
  - `claude/auth/utils.py`, every line that handles deadlines, including `_mirror_login:138-276`;
  - the only production caller, `claude/agent.py:242`.
- **Packet B:**
  - `integration-remaining.diff` in full;
  - `integration-content-audit.json`;
  - `audit_integration.py:9-118`, which includes the merge and graph logic.
- **Results records:** `resume-final-results.json`, `recovery-isolated-result.json`, `claude-parallel-copy-fixed.json`.
- **Rules:**
  - the worktree `AGENTS.md`, grepped (experiments, fixtures, review, Pydantic and settings rules);
  - the `CONTRIBUTING.md` headings, plus its new section in the diff;
  - the root `AGENTS.md` only from earlier in this session.

  These are partial reads, not full ones.
- **Images, all eight opened:** `codex-resume-final-graph`, `claude-resume-final-activity`, `opencode-resume-final-activity`, `codex-advanced`, and the four `recovery-isolated-*` captures (offline, starting, online, real-modal).

## A-R-Q1 (resume edge dropped on import): resolved

- `run_reference` no longer has `show=False`, so upstream's filter that drops edges to hidden fields no longer removes the resume edge.
- `isAgentControlHidden` exposes the port only when there is an incoming edge whose target is this node and whose field is exactly `run_reference`. `run_reference_json` stays hidden even then.
- The Parameters dialog and the inspection panel are given no edge list (`final-settings-fix.diff` installer lines), so Prior Run never shows there.
- Tests cover all three Agent types for:
  - no edges;
  - an edge to another node;
  - an edge into a different field;
  - the JSON field;
  - the port disappearing again after disconnect.

  The builder test now asserts `show: True`.
- The screenshot `codex-resume-final-graph.png` shows Prior Run only on the second, connected node. Its edge comes from the first node's Run Reference. The first node has no Prior Run row.
- `resume-final-results.json` (a record) shows, for all three providers:
  - the same native session before and after, with distinct Activity attempts;
  - `turn_count: 2`;
  - `edge_survives_import_and_reload: true`;
  - controller cleanup confirmed (Codex/OpenCode), or descendant cleanup verified (Claude).
- No selector or automatic choice of prior run was added. Server-side refusal (`prior_run_required`) is unchanged.

## Claude copy serialization: deadline, receipt and credentials preserved

- **Deadline:** `mirror_login` computes the same normal deadline as `_mirror_login` (`min(now + COPY_SECONDS, deadline)`) *before* waiting for the lock. It passes that deadline down, and the inner function recomputes the same minimum. Waiting therefore spends the original 90-second budget and never extends it. The separate `CLEANUP_SECONDS` reserve is still passed unchanged to the SDK session (`:271`).
- **Input checks:** `bool` deadlines and non-finite values are still refused, before the lock is taken, as `claude_local_login_copy_failed`. The inner checks (`:161-162`) are unchanged.
- **Failure release:** the `try/finally` always releases the lock. The test `test_release_after_failure_and_preserve_explicit_deadline` checks this, along with the explicit deadline being passed through.
- **No retries:** a lock timeout raises the existing public code with no copy attempt (checked by a test). The SDK still refuses a receipt in use across processes. No fallback copy and no credential logging were added. The access-only and refresh-ownership rules sit inside `_mirror_login`, which is unchanged.
- **Evidence (records):** before the fix, `ReceiptInUseError` occurred. After it, both concurrent real copies succeeded (1.9s and 1.2s), with 0 model turns submitted.

**A-S-S1 · suggestion · low.** `MIRROR_LOCK` is a process-wide threading lock living in `auth/settings.py`. Under the worktree `AGENTS.md`, settings files hold configuration, so a runtime lock may belong in `utils.py` or a small coordination module. The lock also serializes copies for *different* profiles. That is safe, but unnecessary if several profiles are ever used.

## Error-card fix (`recovery-fix.diff`)

- The new selector hides the background error stack for any `role="dialog"` *not* inside a Radix Popper wrapper. A real modal (Edit Code) still hides the stack (`recovery-isolated-real-modal.png`), and a nonmodal onboarding popover does not (per the record).
- The connection bar turns green only when the service is `ready` and the card is not the model-catalogue card. The test checks the green border colour.
- The `test_packages.py` Langflow bootstrap applies only to the `integrations.langflow.*` and `agents.interface.langflow.*` modules, so core imports gain no framework dependency.

## A-I-G1 (unreviewed integration content): mostly closed

- **Text files, now read:** `.gitattributes`, `CONTRIBUTING.md`, `examples/README.md`, `frontend/langflow-skill-viewer/README.md`, `tests/README.md` and `test_reviewed_cli.py`. These carry the accepted Skills and GitHub text correctly, plus the GitHub archive policy pinned at `714db418`. `test_reviewed_cli.py` keeps its review-hash, base-binding, revocation and scope assertions.
- **The three JSON maps:** the audit script's three-way merge (`audit_integration.py:15-36`) is sound for dictionaries. It flags a conflict whenever values or lists differ on both sides, and the results show none. All three are unchanged since `53c3bf5c`.
- **The five graph files:** the audit shows every field outside the Skill nodes matches *our* (Agent) side exactly. The only other change admitted is the accepted embedded code and hash on the `issue` node from develop.

**A-I-Q2 · question · low** (`audit_integration.py:76-113`)
- The graph audit compares the merge checkpoint against *our* side plus the admitted code changes. If develop changed any other field in those five graphs (a template value, an edge), the result would be dropped and the audit would still report "exactly preserved".
- So it proves nothing was invented. It does not prove develop's non-code graph changes were kept.
- It also checks the graphs at `53c3bf5c`, not HEAD. The maps check covers HEAD; the graphs one doesn't.
- Low risk, because the accepted develop graph changes were presumably code-only. Confirm by diffing develop's base-to-theirs changes for those five files.

**A-D-D2 · docs defect · low · introduced by the integration**
- Where: `frontend/langflow-skill-viewer/README.md:255`.
- It links to `../../examples/opencode-node/README.md`. That folder is retired ("retirement preserved"), and the file does not exist at HEAD.
- Fix: point it at the archived copy on `exp`, or at `docs/features/agents/providers/opencode/activity.md`.

Smaller gaps:
- `AGENTS.md` is listed as resolved but has no hunk in `integration-remaining.diff`, so I assume it's identical to one side. Not verified.
- The deployment parity file (`deployment-parity-final.json`) was not opened.

## Screenshots

- **Codex Resume graph:** layout is fine apart from the missing icons in A-V-Q1.
- **Claude Resume Activity:**
  - two rows, each "1 turn", completed;
  - the selected resume turn shows Unknown for every usage card, "No timestamped usage captured" and "Aggregate usage is incomplete";
  - 8 OpenTelemetry records.

  This is honest. It also shows Claude's resume turn has no usage captured; that limitation should be recorded, not counted as complete telemetry.
- **OpenCode Resume Activity:** two turns, completed, with usage (3,149 / 3,042 / 33, $0.000060). Fine.
- **Codex Advanced controls:** expanded, showing Output Continuation Retries and Runner URL, with no Prior Run. The zoom controls clip the Runner URL label (the known upstream overlay issue, G-V-S2 class).
- **Recovery offline:**
  - the red "Model list could not be loaded" card and the red "Local runner is offline" card stack without overflowing;
  - "previous run's outcome is unconfirmed" is shown;
  - Technical details shows `runner_transport_failed` / `runner_local_offline`;
  - the actions (Start local runner, Dismiss) are separate from the text.
- **Recovery starting:** spinner, "Starting…" disabled, Cancel available.
- **Recovery online:** the runner card turns green, "Run outcome unconfirmed … runner is online. Check the existing run before starting new work". It doesn't claim the task succeeded. The model card stays red.
- **Real modal:** Edit Code covers the canvas and no error cards are visible behind or over it.

**A-V-Q1 · visual question · low/medium**
- In `codex-resume-final-graph.png`, `codex-advanced.png` and the left rail of `opencode-resume-final-activity.png`, icons render as grey rounded placeholders. This affects:
  - the sidebar icons;
  - the node header icon;
  - the info icons;
  - the field action buttons;
  - the zoom controls.
- The earlier approved captures had real icons.
- Either the icon chunk hadn't loaded when captured, or the final build lost icon assets. Please confirm with a capture taken after icons load. `hidden-settings-frontend-build.log` passing doesn't rule this out.

**A-V-Q2 · visual/copy question · medium**
- In `recovery-isolated-online.png`, the green card says "The local runner is online". The red model-list card next to it now says "the app could not confirm it is the configured runner … Do not start a replacement while its identity is uncertain".
- That card's text changed between the starting and online captures, so it was recomputed. Shown together, the two cards contradict each other on whether the runner's identity is confirmed.
- Keeping the catalogue card red is correct. But its explanation should say that model discovery hasn't been retried or has failed, not that the runner's identity is uncertain, unless that really is the state. Which reason code produced that text?

## Verdicts for this packet

- **Implementation: APPROVE.** Covers A-R-Q1, the Claude copy lock, the PopupFrame selector, the recovery colour and the package bootstrap. A-S-S1 is optional.
- **Integration (A-I-G1): APPROVE with A-D-D2 to fix.** A-I-Q2 is a low-risk confirmation.
- **Docs: REVISE**, for A-D-D2 (one-line link fix).
- **Spec:** no change. ACP spec 403 is still an open draft dependency.
- **Visual: APPROVE for:**
  - the Resume edge and port behaviour;
  - the three Resume Activity layouts;
  - modal versus nonmodal shielding;
  - recovery progression and its green/red separation.

  **REVISE/question** for A-V-Q1 (missing icons) and A-V-Q2 (contradictory copy). None of this is task-success or owner acceptance.

## Gates still open

- **This packet's open items:** A-V-Q1 and A-V-Q2 need an answer or a fresh capture. A-D-D2 needs its fix.
- **Evidence I did not open:**
  - `deployment-parity-final.json`, `wheel-result.json`, `interaction-final-tests.json`;
  - the three `*-actual-stop-result.json` files;
  - `model-refresh-browser-results.json`, `claude-parallel-copy-diagnosis.json`, `claude-copy-fix-tests.log`, `native-command-tests-final.log`.

  Their claims (Stop confirmed with cleanup, model Refresh returned HTTP 200, 339-file wheel match, 2,777-file deployment parity) are your reports.
- **Not exercised:** startup cancellation, Docker down or not installed, child-agent capture, native GitHub mediation (issue #215), the split executor, and app-owned OAuth end to end.
- **Typecheck:** full TypeScript still fails on inherited diagnostics (259 candidate vs 265 accepted).
- **Coverage audit:** the final audit across all earlier packets (`prior-reviews/`, runtime packets 1–6, conservation) is still outstanding. I have not read those files, so I can't state the full set of covered files.
- **Separate gates:** ACP spec 403, the 23 held PRs, and your browser validation of the final workflows. PR250 stays unmerged.