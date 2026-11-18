# Native command acceptance (issue 293)

Production branch: `feat/293`; implementation PR amadou-6e/laomedo#301; specification PR amadou-6e/specs#436. These probes belong only to permanent `exp`.

`prepare_image.py` asks the shared registered image owner to build/verify the configured Codex adapter. It submits no model request and imports no credentials.

`chat_accept.py` creates one isolated assistant conversation on the existing acceptance app, submits one real discovery/proposal request, and observes its bounded result. Each invocation creates a new conversation. It never approves a proposal or replays a command. Browser approval is a separate explicit acceptance action. Login tokens stay in memory; private state and captures stay outside Git.

The existing assistant-291 launcher accepts `LAOMEDO_ACCEPTANCE_IMPLEMENTATION` restricted to an isolated workspace worktree. Its default is unchanged. The normal app state/port is preserved by `--resume`; never replace another agent's preview.

2026-11-18 checks: actual new-session catalog timing exposed an asynchronous advertisement race. A two-second bounded observation wait fixed first-turn discovery. Actual status, MCP, skills control commands and model-backed review completed through the human app approval path in the same native thread. A separate test-login proposal had no browser approval controls, as intended. Compact exposed its distinct upstream contextCompaction terminal event and remained unknown under the initial strict turn-completion check; correction/recheck is tracked in PR301. No automatic replay occurred. Acceptance is incomplete until that correction and final independent review.

Implementation checks at b2f6877a: 753 agent tests pass (4 skips); 65 assistant tests pass before focused changes, 20 affected controller/MCP tests and 11 architecture/discovery tests pass; 51 frontend tests and production build pass. CI package tests on Python3.10/3.13, Docker controls, formatting and provider contracts pass. Fixture tests do not replace the live evidence above.
