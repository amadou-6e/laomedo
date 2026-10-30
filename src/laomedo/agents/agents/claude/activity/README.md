# Claude native activity

`ClaudeTelemetry` owns the provider's native telemetry listener and recorded
evidence. Construction binds observation before execution; `bind_thread` binds
native identity, `record` retains normalized evidence, `decode` parses native
telemetry, and `close` stops the exact listener and reconciles its thread.
The HTTP handler lives in the focused
`http/` package with explicit owner state, preserving parse, redaction and lifecycle rules.
Native attribute normalization stays here; common storage must consume canonical
records without interpreting Claude-specific schemas.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `ClaudeTelemetry` | `telemetry.py` | `bind_thread`, `__init__`, `record`, `decode`, `close` |
