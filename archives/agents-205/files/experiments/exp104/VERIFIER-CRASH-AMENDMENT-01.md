# Pre-run bounded reconciliation clarification

Recorded before any execution or pre-run approval of verifier-loss S1. The
original protocol remains unchanged. Replace its "wait at most 20 seconds"
for the restarted cleanup with one synchronous production worker scan using
the production per-command Docker deadlines: inspect 10 seconds, removal
15 seconds, final inspect 10 seconds. The scan must report verified removal;
there is no repeated scan or verification dispatch in this case. The explicit
cleanup time bound is the sum of this fixed command sequence, not an outer
20-second wall deadline that would leave reconciliation running in the
background. Setup/control/final-cleanup commands have 20-second deadlines.
No acceptance threshold, provider/model budget or fresh-identity rule changes.
