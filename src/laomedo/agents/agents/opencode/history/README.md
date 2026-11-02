# OpenCode native history reader

`HistoryReader` reads only bound native session identities after execution
quiesces. `HistorySource`, `NativeExport` and `NativeHistory` in `models.py` are
canonical validated evidence values; `HistoryError` preserves bounded-read errors.

`read(session_id)` exports a consistent bound native tree; `retain` persists the
resulting evidence. Neither submits model work. Exact methods are listed below.
Read limits belong to `settings.py`. Export jobs must not receive
the live credential store. Parent/child attribution, usage equality, capture
completeness and exact cleanup are separate checks; no missing fact is invented.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `HistoryError` | `errors.py` | `__init__` |
| `HistorySource` | `models.py` | Validated fields / inherited interface |
| `NativeExport` | `models.py` | `bind`, `message_ids`, `child_ids`, `tool_calls` |
| `NativeHistory` | `models.py` | `attempt_messages`, `record_fields`, `attempt_sessions`, `terminal_complete` |
| `HistoryReader` | `reader.py` | `__init__`, `read`, `retain` |
| `Settings` | `settings.py` | `settings_customise_sources` |
