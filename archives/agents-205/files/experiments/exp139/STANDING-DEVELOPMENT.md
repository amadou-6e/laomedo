# Repeatable local development demo

The owner approved a standing allowance: four submitted model turns per manual
Run, including timeouts; a fresh host-generated branch; at most one push and
one draft PR per run in `ga84jog/laomedo-exp104-disposable-20261007`.
It persists until disabled. The earlier experiment ledger and consumed write
allowances remain unchanged. This is still the bounded issue-report task, not
arbitrary issue implementation.

## Configuration to activate after independent review

- Start `experiments.exp139.persistent_demo services` and `runner` as independent
  hidden host processes using a new private state folder outside Git.
- The runner listens on loopback port 8780. Existing port 8779 is unchanged.
- Reuse the earlier demo config strictly as a fixture template (it still names
  port 8779 and its historical branch); the standing policy overrides the live
  port to 8780 and generates a new branch for each run. This is not a new
  activation of the earlier campaign.
- Copy trusted baseline source, bundle, pinned skill and frozen issue fixtures;
  create new empty authority, run and per-run budget databases. Never copy or
  reset an old ledger. Record fixture hashes and the reviewed clean source SHA
  in `standing-policy.json`.
- Reuse the existing Codex subscription-login volume and host GitHub connection.
  Credentials never enter the graph. Keep existing command-network policy,
  auth-file denial and `/draft/.git` write permission unchanged.
- Each manual start receives a unique `laomedo-dev-<UUID>` branch. Request-ID
  replay recovers the same run rather than creating another grant. Reject new
  dispatch while a run is prepared or running. Each handoff expires after 600
  seconds; unknown writes consume their allowance and are never retried.
- Disable new launches by setting `enabled` to false in the private policy.
  This does not cancel an active run; use Stop or the existing lease expiry.
- On restart, inherited LocalRunner recovery marks prepared/running records
  interrupted with `runner_restarted`; their ledgers and write budgets remain
  intact. Never redispatch the old request as a new attempt. Inspect unknown
  effects before taking further action.
- Resume is deliberately unsupported on this demo route. Budgets remain durable
  over runner restarts. The first live click belongs to the owner; verification
  uses credential-free fixtures, not that runnable task.

## Readable issue inputs

The frozen issue node shows Selected issue URL and a Task form containing an
`instructions` entry. Advanced Frozen issue context is a nested dictionary,
not Base64. Typed dictionaries preserve backslashes that Langflow's ordinary
text conversion otherwise changes. Hidden legacy encoded inputs remain for
old exported flows. Selecting a different URL without a matching host-frozen
snapshot refuses; this component does not fetch GitHub or accept an arbitrary
issue picker. Snapshot contents must still match their hash.

## Limits

The standing grant is scope control, not protection from another same-user
Windows process. Publication still verifies the exact frozen report and routes
only accepted success. This configuration is local and single-user. It does
not establish hosted isolation or general credential-exfiltration protection.
