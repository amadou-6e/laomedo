# ACP communication

`AcpSession` owns the negotiated protocol session over an already-owned Docker
session; `DockerTransport` adapts bytes to the upstream SDK. `AcpTurn` is the
canonical result value. Providers select policy, not a different transport.

`initialize` negotiates capabilities; `open` creates/loads an admitted native
session; `prompt` submits one turn; `close` releases the protocol connection.
Resume never falls back to fresh. Permission callbacks deny unsupported access;
native notifications/extensions retain their original ordering. SDK callback names
are external contracts, not candidates for cosmetic renaming.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `AcpTurn` | `models.py` | `tool_calls` |
| `AcpSession` | `session.py` | `__init__`, `initialize`, `open`, `configure`, `prompt`, `request_permission`, `session_update`, `ext_method`, `ext_notification`, `close` |
| `DockerTransport` | `transport.py` | `__init__`, `send`, `receive`, `close` |
