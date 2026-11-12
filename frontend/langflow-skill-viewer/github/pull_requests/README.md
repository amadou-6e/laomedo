# GitHub pull request viewer

`PRViewerModal` reads the exact selected pull request through host inspection. Selection parsing is pure; models.ts owns its snapshot contract. The package interface exposes the viewer and selection adapter to upstream controls. Viewing never authorizes a PR operation.

`PRNodeControls` owns saved-template presentation for the canvas and selectors. The overlay installer copies its rendering and native-selector tests into Langflow; run them there with Jest (`PRNodeControls`, `PRSelectors`), alongside `SkillNodeControls`. These are internal controls, not live GitHub acceptance.
