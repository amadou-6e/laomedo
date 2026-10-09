# Phase F: visible Stop cancelled one real prepared run before a native turn

The [frozen Phase F protocol](PHASE-F-PRETHREAD-PROTOCOL.md) and the host
response-hold probe were reviewed before dispatch. The first review found a
late-arrival failure path that could release a prepared worker before cancel.
Commit `0b3053f` fences new starts, cancels every persisted run before opening
the held acknowledgement and leaves an unverified hold closed. A focused
independent recheck cleared that blocker. The [no-model UI preflight](PHASE-F-PREFLIGHT.md)
passed first; the full host suite then passed **366 tests, 9 skipped**.

Tested implementation: `0b3053f2029fd754eb2e9abb2f720be397ab97e3`.
One browser request was reserved under the user-extended shared ledger,
moving it from **5/12 to 6/12**. This passing case made **zero native model
calls**: there is no native thread, native event or runner turn-ledger file.
The pinned Langflow 1.12.3 and Codex image digests, saved flow, embedded
component code, task and pilot skill are recorded in private `pins.json`.

| Check | Observed |
| --- | --- |
| Prepared boundary | The real runner durably saved one `prepared` run while its async HTTP acknowledgement and native worker response gate remained held. |
| Visible Stop and exact identity | One Playground Send and visible Stop click led to one authenticated lookup for request `f43ad59d-5087-4f5f-901a-2c3b7a6da2cd` and one cancel for run `c7125957-1958-4158-a4d3-187f068b1a36`. The cancel followed the click, and terminal status preceded browser-context closure. No host fallback cancel was used. |
| Terminal result | Runner status was `cancelled` with `cancel_confirmed=true` before the acknowledgement was released. Its worker later found that terminal record and did not dispatch. |
| No native launch | `thread_id` absent, zero native events, no container ownership, no runner turn-ledger file, and exactly one run record. Exact cleanup recorded `not_launched`. |
| Teardown and token check | The disposable Langflow UI container was absent; runner cleanup and acknowledgement release were verified. The private browser log/result and sanitized result/teardown did not contain the runner API token. |

Private state: `%LOCALAPPDATA%/Laomedo/exp22-phase-f-live-0b3053f/`.

| Private sanitized artifact | SHA-256 |
| --- | --- |
| `sanitized.json` | `6885d478e567fbccad079a434aa4559c44b0394d78acc1d6eecef0a68d29ef7d` |
| `teardown.json` | `fe1b8ab0870dbf91cb953159d0fb26caf3321b98d838ad677547c48ce738dcc4` |
| `runner-routes.jsonl` | `5415fb4f941a75d38fa6824295399bb4c499467df846754019c3f57b22f3cb6f` |
| `pins.json` | `ffa00c79c05a7b507b81de2ee9f121642c49d8a29efae9bcb3a1b4864278fbfc` |

This passes the bounded **visible Stop before native thread creation** route
with a real prepared runner record. It complements Phase E's active-tool
native interruption; the two are separate one-shot observations. The browser
observer still did not expose a definitive frontend Stop endpoint, and this
test did not create a durable Langflow invocation-to-runner cross-store trace
join. The provider-login volume was present for runner readiness but no Codex
container launched, so this case does not test credential access inside an
agent stage. No real GitHub credential, grant or write was involved. #93's
postrevocation and joint-outage limits remain. No issue state changes from
this result alone.
