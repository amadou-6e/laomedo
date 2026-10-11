# EXP-104 protocol amendment 03 — independent surviving-run control

Status: frozen before the next synthetic process run. The earlier observations
remain historical: `process-observation-v2.json` proves expiry after a lease
service hard kill, but both grants depended on the killed service. It cannot
prove that another run remains usable.

Use two distinct lease-service state directories and processes, each owning
one run grant, with one shared credential-free mediator ledger. Kill only
service A by its exact verified PID. Leave service B running with a continuing
heartbeat. At approximately 0, 15, 30, 45, 60 and 61 seconds after A's kill,
attempt one synthetic write with each grant until A is denied. B must keep
succeeding at every recorded point, including after A is denied. Capture both
service PIDs and liveness, the ordered synthetic provider-call journal, and
monotonic timing. Assert each 200 corresponds to one provider call and no 403
reaches transport. Preserve the previous raw observations without rewriting.

This still uses no GitHub credential or model. It does not replace the frozen
live protocol's runner-loss, scoped identity, actual push/read, negative
controls, or provider-credential retirement cases.
