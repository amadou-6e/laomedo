# Imported Skill history

Importing verified instruction files records an initial immutable entry before
an edit is prepared. Legacy registries without import metadata register their
verified root once and mark the original import time unknown. Retained canonical
ancestors appear in order without inventing original edit provenance.

History uses the operation service and its durable journal, separately from file
inspection. Configure both as described in the [service setup](walkthrough.md#2-start-discovery-and-history-services).
Reload history repeats only the history read after connectivity recovers. It does
not start or configure a service, execute an Agent or rerun the graph.

The journal and registry must be backed up together. Existing commit identities
survive service restarts; deleting the journal loses those identities even when
bundle bytes remain. A backfilled head beyond the initial root requires its exact
Base Commit in the Skill node's Advanced settings before an operation can edit it.
Comparing an unchanged import to current contents shows no file changes.
