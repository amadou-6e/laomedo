# EXP-108 amendment 01: browser repository mismatch control

This amendment is frozen after the first recorded run and before the revised
probe or second run. The first `observation.json` remains historical evidence.

The v1 probe exercises a wrong repository for explicit-token connection, but
not for the browser callback. Add a browser code whose app-user token belongs
to the expected account but is authorized only for another repository. The
callback must be refused, no connection created, and no run capability issued.

The second run writes `observation-v2.json` without overwriting v1. It uses
the same synthetic-only setup, pass criteria, and stop conditions as the
original protocol. Source and evidence hashes will be pinned to committed
bytes. This amendment does not authorize a live credential or claim deployed
browser-flow security.
