# Claude local authentication adapter

The provider-specific `mirror_login` function copies only the authorized access
credential into the dedicated local volume. Host refresh ownership stays on the
host. This is not a generic credential store or permission to copy profiles,
rotating refresh credentials, sessions or settings.

`Settings` reads explicitly supported local opt-in configuration at point of use.
`LocalClaudeLoginError` preserves stable public outcome codes. No README, repr,
dump, graph or validation evidence may contain credential values.

## Current object interface inventory

This inventory names existing methods; the vocabulary above explains their
roles. Full signatures and detailed parameter contracts remain in source.

| Object | Defining module | Public/framework methods |
| --- | --- | --- |
| `LocalClaudeLoginError` | `errors.py` | `__init__` |
| `Settings` | `settings.py` | `settings_customise_sources` |
