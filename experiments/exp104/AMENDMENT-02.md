# EXP-104 protocol amendment 02 — raw call journal and monotonic clocks

Status: frozen before the next synthetic process run. The first machine-written
observation (`process-observation.json`, `b7eb9e1`) is retained as history. It
showed separate-process expiry but included only an aggregate provider-call
count, not the underlying ordered call journal. It is not used as sole proof
that denied requests avoided transport.

The next run keeps the same hard-kill, 0/15/30/45/60-second schedule and
acceptance rule from amendment 01. It adds only evidence capture and a
can-fail consistency check:

- Record every synthetic provider call directly in the observation with
  operation, repository, wall timestamp and monotonic timestamp. Never include
  bearer values, request bodies, token hashes or private paths.
- Record the completed-kill monotonic timestamp and each attempt's monotonic
  timestamp. Schedule intervals on the monotonic clock, not wall time.
- Assert that the number of provider calls equals the number of HTTP 200
  responses. A denied 403 accompanied by a provider call is a failed gate.
- Record the last-renewal-to-kill estimate separately as wall-clock-derived;
  do not use it to assert a subsecond expiry margin. A backwards wall-clock
  step still makes the expiry claim inconclusive.
- The probe writes its own LF-normalized JSON. The committed blob hash, not a
  working-copy hash, is the evidence reference.
