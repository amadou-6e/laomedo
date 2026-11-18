# Native command acceptance (issue 293)

Production branch: `feat/293`; implementation PR amadou-6e/laomedo#301; specification PR amadou-6e/specs#436. These probes belong only to permanent `exp`.

`prepare_image.py` asks the shared registered image owner to build/verify the configured Codex adapter. It submits no model request and imports no credentials.

`chat_accept.py` creates one isolated assistant conversation on the existing acceptance app, submits one real discovery/proposal request, and observes its bounded result. Each invocation creates a new conversation. It never approves a proposal or replays a command. Browser approval is a separate explicit acceptance action. Login tokens stay in memory; private state and captures stay outside Git.

The existing assistant-291 launcher accepts `LAOMEDO_ACCEPTANCE_IMPLEMENTATION` restricted to an isolated workspace worktree. Its default is unchanged. The normal app state/port is preserved by `--resume`; never replace another agent's preview.

2026-11-18 checks: actual new-session catalog timing exposed an asynchronous advertisement race. A two-second bounded observation wait fixed first-turn discovery. Actual status, MCP, skills control commands and model-backed review completed through the human app approval path in the same native thread. A separate test-login proposal had no browser approval controls, as intended. Compact exposed its distinct upstream contextCompaction terminal event and remained unknown under the initial strict turn-completion check; correction/recheck is tracked in PR301. No automatic replay occurred. Acceptance is incomplete until that correction and final independent review.

Implementation checks at b2f6877a: 753 agent tests pass (4 skips); 65 assistant tests pass before focused changes, 20 affected controller/MCP tests and 11 architecture/discovery tests pass; 51 frontend tests and production build pass. CI package tests on Python3.10/3.13, Docker controls, formatting and provider contracts pass. Fixture tests do not replace the live evidence above.


Final acceptance at implementation c9493116: all five admitted commands completed through app approval. The corrected compact receipt retained matching native compaction identifiers and observed the late turn terminal during its bounded drain. A normal message then resumed the same native thread successfully. A further approved review was stopped after positive native turn-start evidence; the native terminal was interrupted, cancellation and exact-container cleanup were confirmed, and the app returned idle. Unknown attempts were never replayed.

The preview supervisor had a stale publication during one restart, preventing inference. `lease_diagnostic.py` restored only that isolated supervisor; its bounded traceback confirmed a normally serving process. The acceptance launcher now requires a fresh supervisor publication and heartbeat instead of trusting an old service.json. This is harness readiness, not a production runner change. No other agent's supervisor was changed.

Final checks: 65 assistant tests, 109 Codex tests (1 skip), 52 frontend tests, 25 architecture tests (1 skip), frontend production build, and registered image build with 13 adapter tests pass. Required Python3.10/3.13 package CI, Docker controls, provider contracts and Black pass at c9493116. Specification and actual screenshot review approved; implementation coverage completion remains pending at time of this checkpoint. No merge authorized.


Capability correction c73d5d5f: new commands3 image explicitly advertises native command execution. Actual older pinned image initialized for the base protocol but exposed no catalog and refused a command before any prompt, with zero model turns and cleanup confirmed. Actual commands3 app approval completed status and compact; compact retained matched native compaction evidence without fabricated assistant text. All required CI and 110 Codex tests (1 skip) pass. Prior complete own-diff, specification and UI review approved c9493116/886b90c; this capability correction and spec12edd8b still require focused recheck, blocked by reviewer quota until 20:00 Berlin on 2026-11-18. Separate pre-existing recovery follow-up is laomedo#303. No merge authorized.

The preview launcher permits explicit LAOMEDO_ACCEPTANCE_REUSE_LEASE=1 for this isolated acceptance supervisor; it checks a fresh heartbeat and does not terminate a separately owned supervisor. Default startup still requires a newly published service.
