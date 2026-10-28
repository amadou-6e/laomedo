# Pull-request visual provenance

| Image | Source | Capture | Evidence boundary |
| --- | --- | --- | --- |
| pr-node.png | Current PR component compiled into a documentation graph | 2026-10-28 | Actual unconfigured form; no GitHub mutation |
| pr-viewer-empty.png | Actual installed PR viewer with no picker selection | 2026-10-28 | Empty state, not a successful provider read |
| create-pr-mock.png | Companion HTML mockup | User-story documentation increment | Proposed new-PR UI; illustrative content, no PR created |

The existing read-only PR inspection returned HTTP 400, so these captures do not
show a populated viewer. No mock response was substituted. Screenshots use
headless Edge; the creation mock is separately labelled. All image and HTML bytes
are unchanged by this reorganization. No graph or external write was requested.
