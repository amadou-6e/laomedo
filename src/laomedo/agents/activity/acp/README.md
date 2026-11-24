# Common ACP capture

`AcpCapture` records the shared protocol stream and retained native extensions.
`begin` binds a native session; `update` retains protocol observations and
`append` / `append_evidence_batch` retain native evidence;
`finish` closes the observed stream. These terms describe evidence, not provider
execution control. Preserve notification ordering, usage scope, redaction and the
distinction between terminal execution and capture completeness.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `AcpCapture` | `capture.py` | `__init__`, `append`, `seal`, `append_evidence_batch`, `begin`, `update`, `finish` |
