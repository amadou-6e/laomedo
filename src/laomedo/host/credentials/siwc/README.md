# Sign-in values and credential custody

`ChatGPTConnection` retains the existing OAuth and refresh state machine.
`OAuthAuthorizationRequest`, `OAuthAttempt`, `OAuthCodeExchange` and
`OAuthAccount` in `models.py` construct related new request/attempt/account data.
`to_query()`, `to_private_payload()` and `to_private_record()` explicitly name
the existing privileged serialization sinks. Tokens, state, nonce, verifier and
credential-bearing URLs are `SecretStr` values excluded from ordinary dumps and
representations. Only those explicit methods unwrap them for the existing local
OAuth/private-file boundary. Refresh ownership and credential mirroring do not change.

These are new-write models, not stricter readers of historical credentials.
Existing account admission, subject matching, scope checks, expiry, refresh
uncertainty and safe error codes remain service-owned. Claims that the existing
verifier passes through without further type checks keep their JSON shape.
Models do not exchange tokens, launch browsers, read credential files or log secrets.
