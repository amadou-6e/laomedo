# Phase G: one real Codex turn through the durable Playground join

This local single-user probe extends the credential-free Phase G restart test.
It uses the existing user-approved private Codex subscription-login volume and
the shared EXP-22 ledger, currently 6/12. Reserve one entry immediately before
the visible Playground Send. An uncertain submission or timeout consumes that
entry. Use one native turn maximum, `gpt-6-luna` at low effort. No GitHub grant,
push credential, or external write is provided.

## Frozen route

Use the checked-in five-node flow only after verifying its embedded component
source byte for byte. Start disposable pinned Langflow 1.12.3 with only the
approved private SQLite `/app/data` mount, read-only component source and a
read-only bridge-token file. The Langflow container must never receive the
runner API token or Codex login. Run an opt-in loopback host bridge with its
private SQLite store and a real local Codex runner with one-turn limit. The
Codex stage uses the previously approved non-split login profile. Perform
preflight without clicking Send or reserving a turn.

The browser imports the saved flow, clicks Send with the unchanged
[Phase E task](PHASE-E-TASK.txt), and waits for an agent-originated long shell
command. The task first checks whether the stage can read `auth.json` without
printing its contents; readable is an immediate failure. The browser clicks
visible Stop after the command begins, before its 30-second sentinel write.
Keep the browser context open until runner terminal observation.

## Required evidence

- One browser Send, one Stop, and runner cancel after Stop begins but before
  browser close; no host fallback cancel may count as UI-originated success.
- One host reservation with exact client, invocation, native request/digest,
  native run ID and raw-event reference; one runner start and no second POST.
- Native `interrupted` event, terminal `cancelled`, exact owned-container
  absence, denied content-free login read and absent late sentinel.
- Remove and recreate disposable Langflow on the same private SQLite mount,
  stop the host bridge and reopen its SQLite binding in a fresh process. Match
  one Langflow trace by saved-flow UUID and reported graph ID in a linked span.
  The span match is corroboration, not executing-graph attestation.
- Record a sanitized summary, hashes, native event count and teardown. Keep
  raw events, token files, login and browser profile outside Git.

If a gate fails after submission, attempt exact host fallback cancel and
cleanup, record the result as inconclusive, and do not retry the ambiguous
request. This test does not prove hosted isolation, semantic task success,
real GitHub credential revocation or the joint-outage bound in #93.
