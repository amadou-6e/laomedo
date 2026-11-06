# GitHub pull request viewer

`PRViewerModal` reads the exact selected pull request through host inspection. Selection parsing is pure; models.ts owns its snapshot contract. The package interface exposes the viewer and selection adapter to upstream controls. Viewing never authorizes a PR operation.
