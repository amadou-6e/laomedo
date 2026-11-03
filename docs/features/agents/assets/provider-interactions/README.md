# Agent provider interactions

Open the [editable provider comparison](provider-custom-code.drawio).
Each tab stacks Codex, Claude and OpenCode vertically at the same scale, with
its relevant file tree beside each provider's graph.

| Tab | Rendered preview |
| --- | --- |
| Run and session | [PNG](comparison-run.png) |
| Tools and credentials | [PNG](comparison-tools-auth.png) |
| Evidence to Activity | [PNG](comparison-evidence.png) |

Scroll vertically to compare providers within a concern. Card titles name the
architectural role consistently; concrete classes, protocols and event formats
appear underneath. Letter references are local to each provider row, not parity
identifiers: absent or additional components retain their actual roles. Matching `[A]`, `[B]`,
etc. references connect graph nodes to their defining files; files shared by
nodes show multiple references. Arrows identify each component's caller, native
interface, credential consumer or evidence consumer.

There is no separate folder tab. Each inline tree includes only the tracked
implementation/policy files relevant to that view and marks them `CUSTOM`.
Codex's modified Moby seccomp profile is marked `CUSTOM + DERIVED`. The adjacent
external/state list identifies every graph node implemented by an installed
dependency, external service or private runtime state rather than repository
source. SDK/CLI dependencies and credential/profile data are not presented as
custom source files. The YAML graph nodes retain their `source_files` mapping
and `graph_reference` so these associations are explicit in the authoring source.

Blue cards identify shared Laomedo code; purple identifies provider-owned Python;
orange identifies custom in-container code; green identifies upstream components
or resources. Arrow labels distinguish control, protocol, credential and evidence
paths. Provider paths such as `claude/agent.py` start at
`src/laomedo/agents/agents/`; abbreviated leaf paths stay within the named provider.
Shared `agents/` and host `host/` paths start at `src/laomedo/`; `docker/` paths
start at the repository root. These are logical architecture/data-flow views,
not every direct function call, protocol response or execution ordering detail.

The run view places the application contract, concrete provider, shared ACP/Docker
adapters and native controller in one path. Claude deliberately shows ACP owned by
its Agent while its container wrapper owns launch policy. OpenCode's two native
cards describe responsibilities of the same process, not two containers.

The tools view connects the credential source to its provider adapter and actual
controller consumer; the command path connects the native tool client, host
broker, shared Docker operations and separate worker. Codex's page shows the
optional split path; its bridge network and unverified native sandbox are explicit.
Normal-mode execution and other admitted login sources are not silently excluded.

The evidence view follows native observations through provider interpretation
into shared Activity and the graph viewer. Claude's OTLP and raw SDK channels are
distinct; OpenCode reconciles post-closure history with provisional ACP capture.
Codex's explicit rollout-export branch ends in a selected artifact, not an invented
automatic Activity import.

Codex's custom TypeScript hooks preserve native events and host policy missing
from the standard ACP contract. Claude uses a packaged upstream ACP adapter but
needs our command bridge, access-only mirror and telemetry receiver. OpenCode
supplies ACP natively; our code isolates commands and reconciles native history.
Its absent maintained Docker recipe/launcher and Codex-worker-image dependency
remain gaps, not necessary properties of OpenCode.

The proposed shared boundary remains documented in the
[parity plan](../../../../architecture/agent-provider-parity-plan.md), which
awaits Claude's review; these comparison tabs describe the inspected implementation.

The inspected runtime baseline is `refactor/205` at `19c7f1f`; subsequent plan
commit `4b9dc1dd` changes documentation only. These diagrams describe source
ownership and logical interactions, not successful runtime or browser acceptance.
Codex split native isolation remains unverified; OpenCode still needs maintained
deployment wiring and a replacement Docker build recipe. Historical receipts
and the presence of local images do not close those gaps.

## Source anchors

- [Shared ACP session](../../../../../src/laomedo/agents/agents/base/acp/session.py)
  composes `connect_to_agent` from the ACP Python SDK.
- [Docker transport](../../../../../src/laomedo/agents/agents/base/acp/transport.py)
  adapts the existing py-docker session's input/output; it creates no container.
- [Codex controller](../../../../../src/laomedo/agents/agents/codex/controller/service.py),
  [Claude Agent](../../../../../src/laomedo/agents/agents/claude/agent.py) and
  [OpenCode boundary](../../../../../src/laomedo/agents/agents/opencode/boundary.py)
  compose the shared communication with native launch/policy and closure.
- [Codex Docker recipe](../../../../../docker/codex-acp/Dockerfile) builds the
  patched adapter; [Claude's recipe](../../../../../docker/claude/Dockerfile)
  installs the packaged adapter. OpenCode's native command is `opencode acp`.

## Editing and export

The nine provider-prefixed YAML files retain the styled graph sources and
source-file metadata. They use the `my-skills/02-graphics/skill-drawio-creation`
renderer (`03-scripts/render_grouped_erd.py`). Preserve saved attachment ports,
orthogonal waypoints and the editable inline file trees when rebuilding.
Each node's `source_files` and `graph_reference` associate tree leaves with graph
nodes; list `external_source` nodes separately.

Assemble the graphs by concern into the three tabs of the single canonical file.
Prefix cell IDs and references with the provider name, group each provider's
cells into its row, preserve row-relative edge geometry, and align file trees.
Use Codex, Claude, OpenCode order and a continuous canvas for vertical scrolling.
Export and inspect all three final tabs with the draw.io desktop CLI; XML validity
alone does not establish visual quality. The PNG previews are exports of that file.

Keep the diagram and its exports aligned with the described revision. Update
the current pages only after implementation changes; do not turn proposed
architecture into an assertion of delivered behavior.
