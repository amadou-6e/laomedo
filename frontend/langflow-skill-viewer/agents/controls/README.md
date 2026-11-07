# Agent graph controls

`RenderAgentInputParameters` adapts upstream input rendering and `AgentAdvancedControls` owns disclosure. Model/dropdown controls use the configured runtime catalogue. Their tests are deployed beside the actual upstream adapters, so relative index/utils imports intentionally bind to those upstream modules. Provider execution and activity capture are outside this package.

The Advanced section contains the four scalar settings: output retries, request
timeout, run timeout and runner URL. A connected supported input stays on the
canvas. Saved graphs can retain a connected Prior Run reference for Resume;
disconnected legacy run-reference controls stay hidden. This is saved-reference
compatibility, not a run selector.

Request identity is assigned automatically, Skill identity/revision belongs to
the Skill node, output requirements come from the downstream contract and the
join bridge is application-owned. Their legacy Agent controls are obsolete,
including formerly connected versions; the viewer does not restore those ports.
Inspection and parameter panels do not expose the hidden compatibility fields.
