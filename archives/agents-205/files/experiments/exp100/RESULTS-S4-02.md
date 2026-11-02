# EXP-100/S4-02: baseline-fetch failure isolated

Issue: [#100](https://github.com/amadou-6e/laomedo/issues/100).
The distinct `EXP-100-S4-02` protocol was frozen at
`9d96847aea4fde238fcda725c5297e5c7072d2ff` before the probe code.
The source head for its one recorded attempt was
`c190b2e72dac2bc3323aeaa838d41c35f79ffdc0`.

The committed `observation-s4-02.json` is direct output; SHA-256:
`299223608741d2096823713a0ae0b10e48c38f02c49410ad1865fef463a4b2ae`.
The diagnostic status is `diagnosed`, **not passed**. The container exited
128. Stage markers show mount access and bare-repository initialization
completed; the failure occurred at `baseline_fetch`, before unbundling or
checking the candidate. Raw Git stderr was intentionally suppressed, so the
precise Git error remains unknown. Ownership or Git safe-directory handling
is a hypothesis, not an observed cause.

The inspected image and resource settings matched the S4 boundary, all binds
were read-only, and cleanup was verified. A later label-filtered container
listing was empty. Generated source and bundle hashes were unchanged. No
provider or model component was instantiated.

Assessment: neither S4-01 nor S4-02 demonstrates a successful bounded Git
import. A corrected transport path needs a **new protocol and identity**,
with an independent pre-run review. The two recorded observations must remain
unchanged. This is not #104 acceptance evidence and does not justify merging
draft #105.
