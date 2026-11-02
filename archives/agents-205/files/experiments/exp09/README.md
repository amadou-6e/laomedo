# EXP-09: synthetic IF-08 replay

This is the zero-model experiment in [Laomedo #39](https://github.com/amadou-6e/laomedo/issues/39).
Its [prospective protocol](PROTOCOL.md) was committed before the probe ran.
The test oracle is the draft T07 at-least-once policy at specs
`6b614e34eac93dea31ce4e80143c001fb4cdd066`, proposed in
[specs PR #203](https://github.com/amadou-6e/specs/pull/203).

Run `python -m unittest experiments.exp09.test_probe -v` and
`python -m experiments.exp09.probe`. Neither command rewrites the committed
[observation](observation.json). Only `python -m experiments.exp09.probe
--record` replaces it, explicitly with LF line endings. The tests compare a
fresh deterministic observation with the committed one.

The probe reuses EXP-05's SQLite raw ingestion and receipt projector, then
builds a read model that labels every provider action's uniqueness uncertain.
It records an exact **delivery** count and preserves duplicate/conflicting
source IDs, keyless reorder, reconnect and separate invocations. A completed
stream may still have unknown unique-action count; a crashed stream remains
partial. The observation contains only synthetic summaries and payload hashes.

This is not a production IF-08 implementation or a real provider replay test.
It does not establish stable source IDs, power-loss durability, IF-07 lifecycle
deduplication, or an actual frontend rendering of the uncertainty label.
