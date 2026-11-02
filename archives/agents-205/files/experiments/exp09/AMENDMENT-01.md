# EXP-09 amendment 01: falsifying control

Issue: https://github.com/amadou-6e/laomedo/issues/39
Date: 2026-10-05
Status: prospective amendment, recorded before the amended probe is run

The frozen protocol's uncertainty assertion could pass by construction: the
EXP-09 read model writes `uncertain` and a null unique-action count, and its
tests check those same literals. This amendment adds a negative control without
changing the original cases, success thresholds, or source data.

Run the historical feasibility #123 source-ID projector on the same synthetic
receipts. Apply the EXP-09 receipt-preservation and uncertainty acceptance
oracle to both projections. The EXP-09 projection must pass. The historical
projector must fail for identical reconnect redelivery because it drops one
receipt, and must reject conflicting source-ID reuse rather than preserve both
receipts. A deliberately asserted unique-action count on an unverified source
must also fail the oracle. Record these failures in the deterministic observation.

This is a harness sensitivity check, not evidence that a real agent provider
supplies stable IDs or that production integration has been implemented. Preserve
the original observation and identify the amended evidence as a later revision.
