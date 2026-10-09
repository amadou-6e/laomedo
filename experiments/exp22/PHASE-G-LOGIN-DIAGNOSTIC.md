# Phase G login diagnosis and repair, 2026-10-09

After the failed turn, the user authorized zero-model network and login checks,
then repairing the private login copy and continuing. The original failed-turn
record stays in [PHASE-G-LIVE-RESULTS.md](PHASE-G-LIVE-RESULTS.md).

The checks used the pinned Codex image `sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239`,
Docker bridge network and UID/GID `10001:10001`. An HTTPS GET to
`https://chatgpt.com/backend-api/wham/usage` used the selected access token and
account header. It submitted no model request and requested no token refresh.
Only HTTP status, known usage fields and allowlisted error categories were
reported; credentials and raw provider responses remain private.

| Check | Observed |
| --- | --- |
| Credential-free network | Docker established verified HTTPS to `chatgpt.com`, `auth.openai.com` and `api.openai.com`; root GET responses were 403, 403 and 421 respectively. These establish connectivity, not authenticated access. |
| Host network | TCP reached all three hosts; Python TLS verification passed for ChatGPT and API, but failed for the auth host. The Docker checks verified TLS for all three; this host-only discrepancy does not explain the container's credential-specific 401. |
| Old private runner copy | Login file present, ChatGPT mode, access-token expiry claim in the future; authenticated usage GET returned 401. A future JWT expiry does not establish that a token is accepted. |
| Current host login | Same usage GET returned 200 with the usage schema, `allowed=true`, `limit_reached=false`. A second check in the same pinned Docker image/network also returned 200. The token was passed in memory through stdin, with no credential file created in that control container. |
| Original native errors | The nine retry events' `additionalDetails`, the final error's message and the terminal error's message contain the allowlisted `unauthorized` and `401` diagnostic words. The earlier categorical summary had no structured HTTP status field; that did not establish the absence of an HTTP rejection. No raw message is published. |
| Repair | With no live container using the auth volume, atomically replaced only `auth.json` from the current host cache via stdin. The destination matched the input, had mode 0600, and its usage check returned 200 with usage allowed. The host cache bytes were unchanged. |
| Budget and cleanup | Zero model turns; shared ledger remained 7/12. Diagnostic containers were removed. No token refresh requested, GitHub credential used or configuration policy changed. |

The evidence identifies rejection of the old runner credential as the practical
blocker. It does not establish why that copy became invalid, prove refresh-token
rotation, or guarantee that a subsequent model stream will work. The independent
host Python auth-host certificate failure is also unresolved. Production login
lifecycle remains with specs #129.

Private sanitized records are under
`%LOCALAPPDATA%/Laomedo/exp22-phase-g-live-20261009-a/`:
`no-model-diagnostic.json`, `no-model-control.json`,
`no-model-same-container-control.json` and `login-handoff.json`. The bounded
continuation and its gates are defined in the
[protocol amendment](PHASE-G-LIVE-PROTOCOL.md#authorized-continuation-after-login-repair-2026-10-09).
