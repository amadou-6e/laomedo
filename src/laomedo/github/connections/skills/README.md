# Private Skill access

This capability composes the existing bounded GitHub reader and immutable Skill
registry for authenticated browser reads. It never dispatches Agents or publishes
to the public source/operation services. Runtime configuration supplies an admitted
private root, outside every public root and Agent mount.

`models.py` owns `PrivateSkillOrigin`, the stored owner/connection/repository,
choice, commit and immutable revision binding. `PrivateSkillResult` pairs one
buffered response with its request-local GitHub read authorization; the HTTP
adapter must install that authorization in the existing response-release fence.

`store.py` owns `PrivateSkillStore`. `retain` imports exact validated bytes into
an owner/connection/repository namespace and journals provenance after immutable
publication. Orphaned bytes from interrupted publication are not discoverable.
`origins` returns only verified scoped provenance; `inspect` requires an exact
stored origin before using the canonical bounded inspector. No public dispatcher
constructs this store. Repeated hashes in different namespaces confer no access.

`service.py` owns `PrivateSkillAccess`. `discover` and `revisions` obtain fresh
online repository authorization, use the bounded object reader, and close its
client. `inspect`, `history` and `compare` reauthorize even warm retained bytes.
All local reads/imports revalidate the browser and connection under the existing
commit lock; the lock is released before returning a fully buffered result, so
response middleware never waits on its own producer. No generator, streaming
response or background task may read private bytes after return. Every successful
response still requires the separate release-time lease/generation/deadline fence.

Private editing/materialization is not enabled by this read capability. Retained
history requires current repository consent, including deliberate reconnection
after a rename/transfer. A missing scoped origin never probes another owner's or
connection's registry. Tests are synthetic controls, not real GitHub acceptance.
