# EXP-22 Phase E: visible Playground Stop to a real native turn

This protocol extends the shared private EXP-22 ledger from four to twelve
submitted turns by the user's explicit instruction. The first four entries are
preserved. Timeouts and ambiguous submissions count. This is a bounded local
single-user test of visible Stop composition, not a hosted isolation claim.

## Frozen boundary

- Use the pinned Langflow 1.12.3 image and the current pinned Codex runner
  image, `gpt-6-luna` at low effort, one immutable pilot skill, and a disposable
  pilot source. Reuse the previously approved private subscription-login volume.
  Do not make another login copy or mount it in Langflow. The Langflow container
  gets only the runner's private API token file, read-only, and custom component
  source, read-only. Its localhost port and auto-login apply only to this
  disposable server; remove it after the probe.
- Use the saved five-node flow. The browser must import that flow into the
  disposable server, open the editor's Playground, submit the frozen task, and
  click the visible `button-stop` after a native long command has started. A
  direct runner or in-process graph cancel cannot substitute for that click.
- The task first attempts a content-free read of `auth.json` and stops if
  readable. It then runs an observable 30-second command that writes a sentinel
  only after the delay. No credential value enters output or committed files.

## Gates and evidence

Before reservation, verify clean reviewed source, private empty state, pinned
images, runner preflight, provider login volume, disposable Langflow health,
flow import and browser Playground availability without clicking Send. The
installed custom-component catalog is not present in this disposable server;
the saved flow embeds the component code, so a separate fake-runner browser
case must prove the component executes before the live turn. A failed gate
spends zero turns. Commit this protocol and
probe, run focused tests, and obtain one independent substantive review before
the first real submission.

Reserve exactly one shared ledger entry immediately before the browser sends.
Observe one runner start and native `commandExecution` start. Only then signal
the browser to click Stop. If it fails to start within 45 seconds, click Stop
anyway and report active-tool cancellation inconclusive. Record browser click
identity and time, Langflow request/job identity if exposed, runner request/run
identity, authenticated lookup/cancel traffic, native interruption, runner
terminal status, partial-event hash/count, exact container absence and sentinel
absence after the original delay. An HTTP 202 alone is not confirmation.
Keep the browser context open until the host observes the runner terminal state.
Require the authenticated cancel to occur after the visible Stop click begins and
before both terminal observation and browser-context closure. A cancel first
seen after disconnect is inconclusive, even if the runner eventually stops.

On every failure after submission, use a host fallback cancel for safety and
exact-owner cleanup, but never count that fallback as UI-originated proof. Do
not retry an ambiguous request. Remove only the named disposable Langflow
container and persist a sanitized teardown. Raw traces, runner token, browser
profile and login stay private outside Git. Publish hashes and redacted facts.

Passing this one composition does not by itself establish a durable cross-store
trace join, a real GitHub credential revocation, or #93 joint-outage behavior.
