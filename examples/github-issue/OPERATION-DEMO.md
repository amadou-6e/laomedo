# Bounded real-agent operation demonstration

Tracking Laomedo#164, under specs#377/decision0010. This is a local example,
not native gh edit/close support or a new production authorization boundary.

The owner approved four submitted Codex turns including timeouts, current
subscription login, and only the following disposable repository changes:
#15 title Filter demo: agent updated, add question and append a short Agent
operation verified section; then close12. No push/PR or other issue is covered.

Prepare freezes both current issue records and exact changes before any turn.
An exclusive campaign lock prevents parallel CLI phases; a leftover lock after
process death is a refusal, never automatically removed to reset the ledger.
The native LocalRunner uses its existing pinned Docker image/auth volume and
unchanged permissions, with a separately started independent lease service.
The standing runner8780 and read-only issue service8783 are unaffected.

The agent is asked to return the approved operations as JSON, without claiming
they already happened or directly using git/gh/network tools. This proves real
Codex proposal -> native evidence closure -> host-mediated modify/close. It
is not a test of autonomous operation selection, native gh syntax, or a saved
Langflow agent graph. The issue viewer can inspect the actual changes afterwards.

Only native completed status, native_trace_closure, complete evidence and ready
snapshot admit the exact JSON. First publication rechecks both original issue
content hashes before minting a target12/15 grant for that native run with60s
expiry. ExactTransport refuses changed payload/expected markers. Stable effect
IDs and the existing journal prevent duplicate dispatch. An uncertain update
never advances to close; all terminal paths revoke the issued grant. No new
model proposal can run once the campaign enters publication. Provider keys and
grant tokens remain on the host outside the copied workspace.

Commands after separate configuration approval:

- `python examples/github-issue/agent_operation_demo.py prepare --state <private-root>`
- Start independent `python -m laomedo.lease_service serve --state <private-root>/lease`.
- `python examples/github-issue/agent_operation_demo.py propose --state <private-root>`
- `python examples/github-issue/agent_operation_demo.py apply --state <private-root>`

Use the package's pinned PyJWT/truststore environment and set PYTHONPATH to this
reviewed checkout. The fresh runner ledger enforces4 across all submissions;
never delete/reset campaign state. Native records/private raw trace remain in
runner/runs. Export only sanitized public outcome and scope evidence. On an
uncertain write, preserve state and reconcile rather than issuing another POST.
