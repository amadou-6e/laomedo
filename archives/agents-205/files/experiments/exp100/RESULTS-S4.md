# EXP-100/S4 recorded result: failed positive import

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100).
Protocol: `PROTOCOL-04.md` at `ec059f73f104b9e9f75e3acc1e4464b60db6dd74`,
with pre-run `AMENDMENT-05.md` at
`abdf5dd08942c69a9f89bee5bd82b0e193f3e4ba`.
The source head for the single `EXP-100-S4-01` recording was
`abdf5dd08942c69a9f89bee5bd82b0e193f3e4ba`.

The committed `observation-s4.json` is the probe's direct output; its SHA-256
is `8fbeede8fbe5f43bac62ab6942f2da9645185c24d48b3685c19f0c7139b327b6`.
The recording exited 1 and the observation status is `failed`. It must not
be retried under the same identity.

The valid-import container exited 128 and produced no success marker. The
probe did not preserve its stderr, so the precise Git failure is unknown.
The 40 MiB write hit the inspected 32 MiB tmpfs limit and emitted
`S4_DISK_LIMIT`. The network diagnostic emitted `S4_NET_DENIED`, but that
marker is not causal evidence of isolation; Docker inspect reported
`NetworkMode=none` for all cases. Inspect also reported the pinned image ID,
128 MiB memory, 32 PIDs, a read-only root, UID 10001, dropped capabilities,
no-new-privileges, and the expected read-only binds. All three containers
were removed and a later label-filtered `docker ps -a` found none. The
generated trusted source and bundle hashes were unchanged. No provider or
model component was instantiated.

Assessment: S4 did **not** establish a successful bounded Git import and
cannot support a product handoff or #104 acceptance claim. A fresh diagnostic
must capture a sanitized stage/error class under a new identity and protocol
before another Docker attempt. This result remains immutable evidence of the
first attempt, including its successful quota and cleanup observations.
