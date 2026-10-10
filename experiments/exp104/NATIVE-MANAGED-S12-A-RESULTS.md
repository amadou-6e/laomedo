# S12 A: consumed, incomplete before agent dispatch

Source1da1f824f348f852d1f1bebf0c150e7c1634d46e; governing specs
ea2558e910d640b802b7b197d2a90b8d14e3249c. Protocole4942d2 preceded
implementation; independent full reviewcb9825d and focused recheck1da1f82
approved one execution contingent green CI38035794920. User-authorized run.

The controller recorded incomplete/ValueError, empty delivery and mutation
lists, zero model turns, and all six cleanup checks true. Original machine
observation is committed unchanged as native-managed-s12-a-observation.json;
SHA-256 c3f2f57597abbafb0f1814378bf2aaf65585c76d6b74f344e2ba6db1bb75f220.
No provider-attempt journal was created. Agent worker never launched.

Coordinator diagnosis (not captured as an exception message): the owned clone
retains its normal origin. configure_remote deliberately refuses an existing
non-mediated remote with mediated_remote_changed. The run reached that call
after managed service readiness and workspace clone, before approval/worker
launch. This is a controller setup defect, not a failed revocation result.
Original observation contains only the exception class; this diagnosis is
source/state inspection, not new machine capture. No remote effect was retried.

Identity exp104-native-managed-s12-20261010-a is consumed forever. The exact
tasks/containers/grants/stages were cleaned; private evidence/root retained.
This result supports no acceptance gate or draft promotion.
