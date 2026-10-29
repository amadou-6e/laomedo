# Shared agent communication

Status: migration in progress. The existing runners have not all been switched.

Laomedo is moving agent execution to one ACP v1 client, using the published
`agent-client-protocol` Python SDK over a creator-owned py-docker stdio session.
Provider-specific policy supplies the image, entry point, credential mounts and
configuration. py-docker remains independent of agents and ACP.

The client advertises no host filesystem or terminal capabilities, rejects every
permission request and extension request, and cannot execute host commands. Model
tools retain each provider's reviewed isolation policy. Claude and OpenCode use
credential-free Docker workers through MCP. Codex retains its constrained native
commands and optional deferred executor. Protocol cancellation is followed by exact container cleanup; an acknowledgement
alone does not prove descendant termination. Failed session loading never creates a
replacement fresh run.

Candidate adapter pins preserve the current CLI families: Codex ACP 2.1.1 with
Codex 0.159.2; Claude Agent ACP 0.98.0 with Claude CLI 2.1.310; OpenCode's native
`opencode acp` in 1.18.33. Candidate validation images are not accepted release
images. Source recipes, package locks and immutable image identities must accompany
the eventual provider cutovers.

Required acceptance paths are Fresh, Resume (including a pre-migration native
session), cancellation during actual worker execution, worker refusal and loss,
authentication failure, dynamic model/effort discovery, pinned skill use, output
precheck, activity capture and cleanup after both normal and interrupted execution.
Codex's separate executor isolation and scoped GitHub mediation must be preserved
or explicitly redesigned and reviewed before removing their old implementations.

Container protocol probes and internal tests support this migration. They do not
establish graph acceptance. Final graph/user-story evidence and owner review remain
required before merging.

## Observable stories and migration evidence

These are acceptance criteria, not claims that the final graph passed. Run each
supported provider through the real node and inspect the resulting activity and
error presentation before requesting owner validation.

| Story | Observable acceptance |
| --- | --- |
| Discover models | The node shows the running CLI's actual models/efforts; discovery submits no model turn. |
| Fresh | One prompt creates one native session, returns the actual answer and workspace changes, and confirms owned container cleanup. |
| Resume | The same node resumes the saved native session, including an existing pre-migration session; its activity shows only the new attempt. Loading failure cannot start a fresh session. |
| Cancel | Cancel during an actual tool command stops the owned execution; status and cleanup evidence agree. Unconfirmed native interruption remains explicitly unconfirmed. |
| Skill | Only selected pinned skills are discoverable; observed tool events establish use, while unused skills remain offered. |
| Output contract | Supported providers reject invalid output, preserve precheck call identity and return a corrected valid submission without repeating an effect. Unsupported providers explain the constraint. |
| Failure/recovery | Missing Docker, unavailable runner, expired credentials, transport loss and worker loss produce descriptive errors and only applicable recovery controls. An uncertain remote outcome cannot offer a blind new turn. |
| Activity | Actual text, reasoning, tools, native identities, usage and provenance remain inspectable across fresh/resume/cancel. Missing native counters or child relationships cannot become invented totals or identities. |

Bounded container-runner evidence currently covers real Claude and OpenCode Fresh,
Resume and cancellation during worker execution. Internal ACP/capture and provider
regressions are separate supporting controls. Codex cutover, locked release images,
pre-migration resume, skill/precheck coverage and final graph evidence remain open.
OpenCode's ACP terminal usage describes the final assistant message rather than
all tool-loop messages; do not present it as a full attempt/session total. Preserving
complete usage and native child-session activity remains a migration requirement.

The owner selected raw Codex event preservation via a bounded ACP adapter
extension. Its raw notification channel must finish before the prompt response is
accepted, apply existing secret redaction and preserve native terminal status.
Host-only extensions for prechecks, typed skills, metadata and the deferred
executor must be allowlisted; no arbitrary native RPC tunnel is permitted.

Upstream references: [ACP transport](https://agentclientprotocol.com/protocol/v1/transports),
[Python SDK](https://github.com/agentclientprotocol/python-sdk),
[Codex adapter](https://github.com/agentclientprotocol/codex-acp),
[Claude adapter](https://github.com/agentclientprotocol/claude-agent-acp),
[OpenCode ACP](https://opencode.ai/docs/acp/).
