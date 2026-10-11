# EXP-100/S4-03: bounded small-fixture import passed

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100).
`PROTOCOL-06.md` was frozen at
`c7cd911a3c5c7cfd60a818f422c9e54ee3ef9e9d` before the probe code.
The source head for the one `EXP-100-S4-03` recording was
`79533a262799479f7eb1ee86fad055075308e205`.

The committed `observation-s4-03.json` is direct output; SHA-256:
`a50e56b66cd77077e84814cd8a404343dfdce9d5a2c51d4c293472a5d0739c81`.
It records `passed`: the baseline bundle and candidate bundle both imported
under Git 2.39.5, the exact commit IDs were checked, strict fsck and
baseline ancestry completed, and the container exited 0 with `S4_VERIFIED`.
Local no-Docker preflight had also passed. Both bundle hashes were unchanged.

Docker inspect confirmed the pinned image ID, `NetworkMode=none`, read-only
root, 128 MiB memory, 32 PIDs, UID 10001, dropped capabilities,
no-new-privileges, a 32 MiB tmpfs, and exactly three read-only binds:
`/baseline.bundle`, `/input.bundle` and `/verify.sh`. The recorded container
cleanup was verified, and a later label-filtered `docker ps -a` found no S4
containers. No provider or model component was instantiated.

The earlier S4-01 failed import and S4-02 `baseline_fetch` diagnosis remain
unchanged and are not represented as passes. S4-01 also observed a working
32 MiB tmpfs quota control under the same image and settings, but S4-03 did
not repeat that control. This candidate bundle was complete, not thin; the
test does not establish imports that depend on baseline objects.

Assessment: a small fixture can be imported using two bundle files under
this configured disposable resource boundary. The result does **not** prove
adversarial-pack OOM resistance, a durable product handoff, a grant-bound
staged commit, remote push safety, literal `git`/`gh` parity, production
service-manager survival, a live #104 runner-loss outcome, or readiness to
merge draft #105. Those require separate implementation and acceptance
evidence.
