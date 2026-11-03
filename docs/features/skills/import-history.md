# Imported Skill history

Importing verified instruction files creates an initial immutable history entry
before an edit is prepared. A retained import without its original timestamp is
labelled **original import time unknown**; registering it does not invent an
import time or rewrite existing commit identities. Comparing an unchanged import
with current contents shows no file changes.

History uses the operation service and retained journal, separately from file
inspection. Configure both connections as described in the
[service setup](walkthrough.md#2-start-discovery-and-history-services). Retry can
reload a recovered connection; it does not start or configure that service.

## Historical verification

These are actual earlier captures from the Skill history work at
`859079dfd13e7f55dda56ea75373032a93357fec`, retained from PR #248 and moved here
because Skills owns the behavior. They are historical evidence, not acceptance
of the independent Skills extraction.

![Existing imported root with explicitly unknown original timestamp](assets/import-history.png)

![Fresh initial import compared with unchanged current contents](assets/initial-import.png)

The earlier installed history-service wheel was
`ccd9ccdb5434fa229cce7a110447b97527c89f54afc633f4f1410e33071c4f1d`.
The real workflow checked a fresh import before editing, verified the complete
root diff, refreshed, restarted the exact history service and retained the same
commit IDs. A real outage and Retry recovered in 206 ms without duplicate roots.
No Skill edit, Agent dispatch or new GitHub effect occurred during that check.
The app and other services retained their separately recorded versions.

Compatibility controls also cover verified canonical revisions predating the
journal. Those are internal regressions; they do not establish a fresh Agent
operation or the current extraction's browser acceptance.
