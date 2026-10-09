# Phase G: pinned Langflow server identity observation

The [Phase G protocol](PHASE-G-CORRELATION-PROTOCOL.md) was frozen at `e52194a`
before this credential-free test. This is gate 1 only, using the pinned
Langflow 1.12.3 image and a disposable local fake runner. The test imported
one saved five-node flow, invoked it twice through Langflow's `/api/v1/run`
endpoint, and captured the component's graph run ID, saved flow ID, and stage
ID in the fake runner request. It made **zero model calls** and did not advance
the shared **6/12** turn ledger. The API route is not a Playground Stop run.

| Observation | Result |
| --- | --- |
| Fake runner dispatches | 2, one per API invocation |
| Graph run IDs | Two distinct UUIDs |
| Saved flow ID | Same UUID in both component calls, matching the imported flow |
| Stage ID | Same configured node ID in both calls |
| Langflow SQLite | A read-only [snapshot inspector](phase_g_inspect_snapshot.py) found both graph run ID strings in `span.inputs`, `span.outputs`, and `message.session_metadata`. One also occurred in `vertex_build.data`. The saved flow ID string occurred in `message.session_id` and `trace.session_id`, among other columns. These are substring matches, not proof that every matching column defines a stable identity relationship. |
| Teardown | Disposable Langflow container absent; fake runner stopped |
| Token check | Fake runner token absent from the private sanitized summary and teardown |

The in-process `Graph.from_payload` test separately observed no saved flow ID.
A second `arun` call on the same graph object did not dispatch the component,
so that attempt did not establish what Langflow would do with a reused graph
object. The installed server API route gave distinct graph run IDs for two
separate invocations of one saved flow. The exact SQLite rows are private;
the matching values may be nested in message or span payloads. Their presence
shows those strings reached the saved database in this one disposable run,
not that Langflow attests them as stable IDs or that a Laomedo invocation has
been durably bound to a runner request.

Private state: `%LOCALAPPDATA%/Laomedo/exp22-phase-g-identity-20261009-d/`.
It contains a disposable Langflow database snapshot and fake API credential;
neither is committed. SHA-256: `identity-summary.json`
`7a395f6bf4317d282c833ea18d3ade16379600cc251a41e6a46524ea1bf5b38b`,
`langflow-snapshot.db`
`1d809a0632814d7e16e5891b4adc6d5adac07d58c2056650aa19149800685e9d`,
and `teardown.json`
`e9dfbaed41efca2752c3df2f551899796c1b08377ea34f3c61e782990d6b8f61`.
The read-only inspector's sanitized `identity-locations.json` is
`fdff56155e90aa63870fe940513b2cadb8a86e4f5f42d254eff8107f4db2821a`.

The first attempt at this server probe was refused by Langflow `/run` with 403
before any fake runner dispatch because it supplied only the disposable
auto-login bearer. The successful attempts also supplied a disposable Langflow
API key kept in memory. The originally intended `/app/langflow` host mount was
empty; this image's default SQLite URL points into its site-packages tree. The
test took a private SQLite backup before container teardown, rather than
claiming that the empty host mount preserved state across restart.

The host suite passed **366 tests, 8 skipped**, and the pinned Langflow
custom-node suite passed **19 tests**. Gate 2 remains: a durable pre-dispatch
Laomedo invocation reservation and runner acknowledgement binding must survive
restart without redispatch. No Phase E/F result is upgraded by this observation.
