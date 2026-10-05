# EXP-66 amendment 01: retain source row for hash verification

This amendment is committed **after** the first live run and **before** a
separate diagnostic replication. The first observation is retained at its
original commit and is not passed off as final hash-verifiable evidence.

The first run produced one `408`, four `JOB_FAILED` reads, one delayed runner
effect and a durable partial trace after reopening. Its effect receipt has a
`sha256:` source reference computed from the runner journal row, but the
observation retained only that row's event type and UTC time. The temporary
journal was removed with the volume. A reader therefore cannot recompute
the source-reference hash from the committed observation.

Authorize exactly **one** further one-call, four-poll, zero-model replication
under [the frozen protocol](PROTOCOL.md). The only capture change is to retain
the runner's sanitized `case`, `event`, `utc` and container `monotonic` fields
for each journal row. The exact effect-row JSON canonicalization and SHA-256
must be checked against the trace receipt in a falsifying test. The image,
timeouts, poll offsets, no-retry rule, endpoint and one-container cleanup
remain unchanged. No additional real-agent or external action is authorized.
