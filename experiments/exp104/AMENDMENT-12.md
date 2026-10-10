# EXP-104 amendment 12: isolated push classification and nonblocking revocation

Date: 2026-10-07. Status: frozen before any new live effect. The D2 `-01`
and `-02` identities remain consumed; neither is retried or relabelled.

Independent review of draft #105 identified two blocking paths. The Git
workflow-file check could read replacement objects from the checkout while
the push staged real objects. A serial Docker cleanup could delay a second
run's renewal or admission. The next code revision must classify the exact
objects in an isolated staging repository with replacement objects disabled,
and must revoke before starting cleanup outside the lease scan loop. A
regression test must use a Git replace ref to hide a workflow edit; another
must hold cleanup open while a second run is used and a third is admitted.

The fresh candidate identity is `exp104-s3-20261007-01`, with branches
`exp104-s3-20261007-01-{a,b,c}` and connection ID
`exp104-s3-selected-gh`. It uses the user-selected `GH_LAOMEDO` key from the
host-only `.env` file. The token bytes and hash never enter this repository,
an agent mount, a command line, or the result. The target is only
`ga84jog/laomedo-exp104-disposable-20261007` (repository ID 1408647759),
whose `main` baseline is `1f1a505f2fbd31993a7946924a9bec5a27bb15c1`.
The exact code SHA is supplied and checked at launch. A missing, broad, or
unverifiable provider-enforced repository scope stops the scoped candidate
before any write. A token that can reach the repository is **not** by itself
proof of that scope; record the user's repository-selection confirmation.

The one-shot sequence remains [LIVE-PROTOCOL.md](LIVE-PROTOCOL.md), except
that the probe now waits for a durable `revoked.json` checkpoint, tests A's
post-loss denial and provider-attempt count, then waits for the exact
container cleanup result. Capture the container's state at the denial.
This separates revocation evidence from cleanup completion. Do not retry a
push, PR, or issue effect with an uncertain response. No model turn is used.

The selected file-backed token custody, synthetic runner, and manual launch
of the two host services remain experimental. Even a scoped-token pass is
not production account connection, deployed-service, full `git`/`gh`
capability, or real-agent cancellation evidence. Draft #97/#105 and Q11
stay open until their separate gates are met.
