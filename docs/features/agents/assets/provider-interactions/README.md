# Agent provider interactions

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

The three numbered YAML files are the styled graph sources. They use the
`my-skills/02-graphics/skill-drawio-creation` renderer. Rebuild each page with
`03-scripts/render_grouped_erd.py`, then retain its editable `mxGraphModel` as a
page in the combined file. Manual layout corrections in the combined file must
also be preserved when rebuilding. Export and inspect every final page with the
draw.io desktop CLI; XML validity alone does not establish visual quality.

Keep the diagram and its exports aligned with the described revision. Update
the current pages only after implementation changes; do not turn proposed
architecture into an assertion of delivered behavior.
