# EXP-65 amendment 01: classify the status-read 500

This amendment is committed **after** the first one-call probe and **before**
any diagnostic replication. It does not alter the frozen Langflow image, flow,
one v2 invocation, timeout values, endpoint delay, poll offsets, zero-model
scope or cleanup rule in [PROTOCOL.md](PROTOCOL.md).

The first run returned `408` and later recorded one effect, but all four
read-only job-status lookups returned HTTP 500. The first capture retained the
HTTP status and top-level response keys, but not the `detail.code`. In the
pinned Langflow handler, `500` can represent a failed workflow job or an
internal error while reading/processing status. Thus the first result cannot
distinguish those mechanisms.

Authorize exactly **one separate four-poll, one-invocation diagnostic run**
under the same limits. Capture only whitelisted `detail.code`, `detail.error`,
`detail.message`, and the *presence/type* of `detail.error_detail`; do not
retain provider payloads or credentials. Preserve the first observation as
historical evidence. A second `500` remains a negative job-queryability
result even if its cause is identified. Do not infer an IF-06/07 trace from
Langflow's native job API and do not repeat the timed-out POST again.
