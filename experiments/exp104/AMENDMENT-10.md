# EXP-104 amendment 10: preserve partial evidence and use a fresh identity

Date: 2026-10-07. Status: frozen before any follow-up container or GitHub
request. Applies only to the broad-token D2 diagnostic, not the original
repository-scoped acceptance protocol.

The first D2 identity, `exp104-d2-20261007-01`, is consumed and must never be
rerun. Its one mediated A push was confirmed and independently read back at
commit `919fc96cd89ac5c972a36cef4296780544133a8b`. The non-secret provider
journal shows exactly one push and two reads; it shows no post-revocation
push. A's lease result reports `heartbeat_lost`, revocation, and verified
exact-container removal. B's result reports `service_restart` and verified
removal. A new C lease was accepted but its container was never observed;
the probe stopped on `ready_timeout`. The recorded observation lacks the
exact runner-kill timestamp because the harness wrote progress only on full
completion. Therefore this first run is **incomplete**, not a 60-second
acceptance result or a full D2 pass. Its A branch is left intact.

Before another GitHub effect, a local-only disposable Docker launch using the
same pinned image and runtime flags may diagnose the C failure. It must use a
fresh exact container name, no credentials or mounts, and remove only that
container after checking its identity. This is not an EXP-104 case or a model
turn.

The follow-up probe uses the new, never-used identity
`exp104-d2-20261007-02`, with fresh A/B/C branches, run IDs, lease tokens,
containers, private state and observation path. The script now saves a
sanitized progress record after each meaningful phase; a failed run retains
that progress in its observation. A runner startup failure records a safe
error code and keeps raw Docker stderr only in private local state for review.
The original no-retry rule still applies: no write from identity 01 is sent
again, and an ambiguous effect in identity 02 ends that run without retry.
