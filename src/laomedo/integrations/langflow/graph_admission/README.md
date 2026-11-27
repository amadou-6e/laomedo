# Saved-account graph admission

This package decides whether a native Langflow graph may run with saved GitHub
accounts. It validates every component's source against a pinned host catalog
and derives the approval bounds of each Issue/PR node from the effective graph
that will execute. It authorizes no GitHub operation itself: the selections it
produces go to `GitHubRunAuthority` in
[`laomedo.github.node_runs`](../../../github/node_runs/README.md). It is not
authentication; the browser run scope comes from `../authentication/`.

## Layout and objects

```text
graph_admission/
  settings.py   GITHUB_GRAPH_COMPONENT_TYPES (host-owned execution classification)
  models.py     GitHubCatalogEntry, GitHubCatalogSnapshot, ResourceBinding
  catalog.py    GitHubGraphCatalog
  node_runs.py  GitHubNodeRunAdmission
```

The isolated worker (`../execution/worker/`) imports `GitHubCatalogSnapshot` for
its bootstrap and re-runs `GitHubGraphCatalog` and
`GitHubNodeRunAdmission.executable_graph` on the actual parsed graph.
`ResourceBinding` is the canonical data-only Skill revision or registered-MCP
configuration epoch. It carries no endpoint or credential and imports no server
authentication or database models. Host authoring resolves its ownership;
transporting the reference grants no authority by itself.

## Catalog

`settings.py` holds the explicit classification: unknown types, runtime flow
loaders and host-Python execution components remain refused. Add a canonical
host catalog type only after checking its execution behavior.

`GitHubCatalogEntry` is one canonical component type, its classification and the
SHA-256 of its executable source. `GitHubCatalogSnapshot` is the frozen tuple of
entries pinned across one saved-account run.

`catalog.py` owns `GitHubGraphCatalog`. `capture` copies exact code digests for
canonical entries from a trusted host catalog; neither posted labels nor posted
hashes are inputs. The caller owns registry provenance: `capture` must never
receive a browser template or an untrusted worker's catalog response.
`effective_graph` validates all leaf nodes, including disconnected and nested
nodes, then uses native pure-data group expansion and validates the resulting
code again after proxy input overrides. The same immutable catalog snapshot
must be retained for admission and worker construction. This does not itself
establish OS isolation or authorize a GitHub operation. `classification`
resolves canonical catalog identity without trusting posted component names or
parsing extension labels.

## Node-run admission

`node_runs.py` owns `GitHubNodeRunAdmission`, the native graph projection for
saved-account approval. `executable_graph` removes only known canvas geometry;
`effective_graph` first requires the supplied trusted catalog to validate and
expand the complete graph, including disconnected leaves. `prepare` always uses
that projection and the catalog's canonical classification, never a posted name.

`prepare` extracts account, repository, picker target and write-capable input
edges from the same effective graph that will execute. The template field names
come from the GitHub contracts (`laomedo.github.contract`,
`laomedo.github.issues.contract`, `laomedo.github.pull_requests.contract`), which
the components also use to declare their inputs. The saved-account selector
field (`GITHUB_CONNECTION_FIELD`) is not declared by the components yet: an
Issue/PR node without it is refused rather than treated as host-authenticated.
Before the selector is added, the components' fallback outside an isolated worker
must also refuse any non-host connection (review note N2 on PR #287).

`prepare` passes canonical `GitHubNodeSelection` values to the run authority
rather than accepting a browser-supplied target list. Edges use current native
`data` handle objects; obsolete string handles are not supported by this path.
Static requests are also write-capable; earlier PR operation outcomes never
become requests. Saved-account Issue/PR components have no Agent tool interface,
so Tool Mode is refused rather than bypassing graph approval.
