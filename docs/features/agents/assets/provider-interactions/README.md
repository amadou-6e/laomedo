# Agent provider interactions

For an explanation of custom code, use the individual provider diagrams:

| Provider | Editable diagram | Run/session | Tools/credentials | Evidence/Activity |
| --- | --- | --- | --- | --- |
| Codex | [Codex](codex-custom-code.drawio) | [PNG](codex-custom-code.png) | [PNG](codex-tools-auth.png) | [PNG](codex-evidence.png) |
| Claude | [Claude](claude-custom-code.drawio) | [PNG](claude-custom-code.png) | [PNG](claude-tools-auth.png) | [PNG](claude-evidence.png) |
| OpenCode | [OpenCode](opencode-custom-code.drawio) | [PNG](opencode-custom-code.png) | [PNG](opencode-tools-auth.png) | [PNG](opencode-evidence.png) |

Each provider file has four pages: run/session, tools/credentials,
evidence-to-Activity and the tracked provider/Docker folder structure. The first
three replace the detached supporting-code cards. Every
implementation or resource card participates in its page's architecture; arrows
identify its caller, native interface, credential consumer or evidence consumer.
The pages are also collected in [one twelve-page file](provider-custom-code.drawio).

Folder-page previews: [Codex](codex-folders.png), [Claude](claude-folders.png),
[OpenCode](opencode-folders.png). Each tracked file has an ownership marker;
custom implementation, package/test code and build/policy files are distinguished
from generated locks, documentation and upstream licences. Codex's modified Moby
seccomp profile is explicitly marked custom plus derived. RUN, TOOLS / AUTH and
EVIDENCE connect the file inventory to the architecture tabs. The OpenCode page
marks its absent Docker recipe as missing, not an implemented folder. Installed
SDK/CLI/adapter source is identified as external to this tracked tree.

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

Open [the editable draw.io diagram](agent-provider-interactions.drawio).
Its three pages separate the inspected implementation from the proposed design:

1. **Current interaction stack**: Laomedo Python, the ACP Python SDK, Docker
   transport, py-docker, Docker SDK, Engine and provider controller. Green edges
   show Agent communication; dashed blue edges show Docker control/attached I/O.
   ACP messages travel through the Docker-attached stdin/stdout session; ACP is
   not a Docker lifecycle API. The model service is outside the local controller.
2. **Current provider differences**: the common ACP client connects to a patched
   Codex adapter, a packaged Claude adapter or OpenCode's native ACP server.
   Native tool-execution adapters and deployment gaps are shown separately.
   These are responsibility/delegation paths, not a sequence diagram. Limitation
   cards are annotations, not calls. Provider network requests originate in the
   native controller; credential-free workers execute admitted commands.
3. **Proposed parity boundary**: the planned shared application/lifecycle contract
   and small provider runtimes. This page is **PROPOSED / NOT IMPLEMENTED** and
   awaits Claude's review of the [parity plan](../../../../architecture/agent-provider-parity-plan.md).

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

The numbered overview YAML files and the provider-prefixed YAML files are the
styled graph sources. They use the
`my-skills/02-graphics/skill-drawio-creation` renderer. Rebuild each page with
`03-scripts/render_grouped_erd.py`, then retain its editable `mxGraphModel` as a
page in the combined file. Provider pages use their saved attachment ports and
orthogonal waypoints. Rebuild all three provider pages before assembling each
provider file and the nine-page collection. Manual layout corrections in the combined file must
also be preserved when rebuilding. Export and inspect every final page with the
draw.io desktop CLI; XML validity alone does not establish visual quality.

Keep the diagram and its exports aligned with the described revision. Update
the current pages only after implementation changes; do not turn proposed
architecture into an assertion of delivered behavior.
