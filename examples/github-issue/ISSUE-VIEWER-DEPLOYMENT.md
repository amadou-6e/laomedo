# Issue viewer activation draft

Not applied. Replace only the reviewed viewer source/frontend mounts on port7864,
retaining saved flows, database, login, all components, skill registry/service8782,
issue service8783 and runner8780. The two Issue controls replace Code only for
GitHub Issue. Keep the previous container for rollback and compare owned flow
hashes before/after. The new authenticated inspect route performs read-only
calls through the existing issue service. No write bindings are enabled by this
viewer deployment and no model turn is spent.

The real operation demonstration is separate. Prepare a clean private campaign
state outside Git. Use the pinned existing Codex Docker image/auth volume with
unchanged runner permissions and a separate independent lease service. The
runner submits at most four turns, counting timeouts, and preserves its ledger.
The agent proposes the exact approved #15 title/body/question-label update and
#12 close as JSON. Only after native evidence closes and that output matches the
frozen approved payloads does the host bind an issue_update capability to that
native run, target numbers12/15 and a 60-second expiry. Apply the two operations
through GitHubIssueGateway using stable effect IDs, preserving unknown outcomes.
The agent never receives the GitHub key or write capability. Compare original
issue update markers before mutation; refuse concurrent change. A failed or
uncertain update never advances to close; no uncertain operation is retried.
This is agent-directed, host-mediated execution, not new native gh CLI syntax.
No push, PR, other issue or permanent write enablement is authorized. Current
read-only preview8783 bindings and standing publication flow remain unchanged.
