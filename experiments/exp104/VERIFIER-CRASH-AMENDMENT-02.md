# Preserve pre-pause S1; freeze fresh S2

Prospective 2026-10-09, before changing the probe identity and before any S2
execution. S1 at f0ba073a8f5fce6356dc7784543d147bb4e14f11 stopped before
the deliberate pause. Its observation and cleanup remain historical; no
worker was killed in the intended crash case. S1 is consumed, not retried.

Fresh identity: `exp104-verifier-loss-s2-20261009`. Original case/outcome rules
and Amendment 01 remain. New implementation adcb3ae stages an LF-normalized
trusted shell resource with fixed SHA-256
`5a7c32be96594c5a5ee3341f2870e85d83673860ec515996928e6badfb4368f5`
before Docker creation instead of mounting checkout bytes. Source input may
be LF or CRLF; any other normalized bytes fail before container dispatch.
This repairs the effective-byte discrepancy found after S1, not a change to
the verification algorithm or acceptance criteria. Freeze exact S2 code and
obtain independent pre-run approval. No model/provider authorization added.

Results must distinguish source ordering evidence (reservation occurs before
create in reviewed code) from runtime presence at kill. Only captured ID/state
fields support the observation; do not imply names/labels/timestamps were
independently captured when the probe does not emit them.
