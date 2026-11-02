# EXP-09 prospective replay protocol

Issue: https://github.com/amadou-6e/laomedo/issues/39
Selected draft oracle: specs `6b614e34eac93dea31ce4e80143c001fb4cdd066`,
`projects/laomedo/decisions/0003-agent-event-replay.md` and
`projects/laomedo/subsystems/run-traces/contract/interfaces.md`.
Source base before this experiment: Laomedo
`89d0dd6b2881179ec61ba58e4307221f7a21d79b` (`develop`).

## Question and falsifier

Can the bounded SQLite ingest and read projection preserve each committed
IF-08 delivery, including redelivery and conflicts, without presenting a
confirmed unique provider action where source identity is unverified?

Fail if a committed raw receipt is absent from the read projection, a
repeated ID with a different payload is collapsed, a keyless or repeated
delivery is labeled confirmed unique, a receipt sequence is used as a native
identity, or stream completeness is inferred from action uniqueness.

## Frozen synthetic cases

1. Repeat an identical event with a source ID across a new `EvidenceStore`
   instance (reconnect). Expect two raw receipts and two receipt-backed display
   records, no confirmed unique-action count.
2. Reuse one source ID with conflicting payloads. Expect both payload digests
   and both summaries preserved, no source-ID overwrite.
3. Deliver a keyless tool result before its call, then redeliver the result.
   Expect receipt order preserved and all action identities uncertain; no
   inferred call/result relationship from order alone. End with a crash sweep,
   so the stream is partial.
4. Use the same call ID in a call and a result, and the same source event ID
   in two distinct invocations. Expect no cross-invocation collapse and no
   assumption that a call ID alone is an event identity.
5. Reproject each case twice. Expect no extra stored projection, no raw-row
   change, and the same read result. A completed invocation may have an
   uncertain unique-action count; a crashed one remains partial.

The probe will use only synthetic strings/payloads and temporary SQLite
databases (`WAL`, `synchronous=FULL` as in EXP-05). It will record a sanitized,
deterministic observation without run IDs, secrets or raw provider content.
No model turns, Docker, Langflow server or GitHub writes are used by the probe.

## Pass boundary and limits

Passing these cases validates only the pinned synthetic ingest/projection
path. It does not prove a real Codex/Claude source supplies stable IDs,
actual reconnect redelivery, acknowledged-event power-loss durability, or
IF-07 lifecycle deduplication (T10). The existing feasibility #123 projector
assumed stable source IDs; it is a historical negative comparator, not the
production implementation being changed here.

The protocol is frozen before execution. Any changed case or threshold needs
a visible amendment rather than silently rewriting this record.
