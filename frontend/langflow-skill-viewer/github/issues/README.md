# GitHub issue viewer

`IssueViewerModal` reads the exact selected issue through the host inspection boundary. Selection parsing is pure and never authorizes a mutation. Wire snapshots are owned by models.ts. The upstream modal entry point is this package interface; reads preserve the selected identity and abort on close or selection change.
