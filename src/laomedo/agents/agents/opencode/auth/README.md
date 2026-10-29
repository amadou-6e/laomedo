# OpenCode authentication adapter

Provider-specific login selection and freshness validation live here. This code
does not become generic host storage simply because trusted host startup calls it.
`NoRedirect` is the explicit HTTP policy object; `redirect_request` is a required
urllib hook. Login data remains private and excluded from graphs and diagnostics.
Supported subscription/authentication behavior and stable failures are preserved
when extracting service objects from the existing function implementation.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `NoRedirect` | `transport.py` | `redirect_request` |
